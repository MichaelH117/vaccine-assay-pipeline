"""Append-only audit trail for the mini-LIMS (owner: GxP Validation Engineer seat).

This is the ONLY supported write path into the audited base tables (``lims.*`` and ``assay.*``).

Controls implemented here (see ADR 001 and docs/validation/):

* Preventive: the API offers ``insert_records`` and ``correct_record`` only. ``update`` and ``delete`` exist only to
  raise ``AppendOnlyError`` (AC-3.2). ``insert_records`` refuses duplicate keys, so a record can never be silently
  overwritten by a second insert.
* Attributable / why: every audit row carries ``performed_by`` and ``reason``; blank values are refused.
* Detective: every audit row stores ``prev_hash`` and ``row_hash`` (a SHA-256 hash chain). ``verify_chain`` recomputes
  the chain and names the first broken row (AC-3.3, INJ-7).

* Detective (records): ``reconcile`` compares every live base-table row with the canonical JSON stored in its INSERT
  audit row, so a direct SQL edit, delete or insert on a ``lims.*`` / ``assay.*`` table is found (BUG-005).
* Detective (tail): every audited write also appends a row to ``audit.chain_checkpoint`` (head seq + head hash), and
  ``verify_chain`` can also check an external, write-once anchor file (``pipeline.integrity.write_chain_anchor``), so
  deleting or re-hashing the newest rows is found (BUG-004).

Known limitation (ADR 001, DESIGN R1): DuckDB has no triggers or REVOKE. Anyone with the database file can still run
SQL directly. These checks detect that; they do not prevent it. Someone who edits a base row AND its audit row AND
re-hashes the chain AND the checkpoints is caught only by the external anchor, and only if the anchor file is kept
out of their reach.

Hash rule (DESIGN 3.2): ``row_hash = sha256(prev_hash + "|" + canonical_content)``, where canonical_content is every
audit_log column except the two hashes, as JSON with sorted keys and ISO timestamps. The first row has
``prev_hash = "0" * 64``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, NoReturn

import numpy as np
import pandas as pd

GENESIS_HASH = "0" * 64
AUDIT_LOG = "audit.audit_log"

# Columns that go into the hash, in contract order (DESIGN 3.2). The hashes themselves are excluded.
HASHED_COLUMNS = [
    "audit_seq",
    "table_name",
    "record_key",
    "action",
    "field",
    "old_value",
    "new_value",
    "performed_by",
    "reason",
    "audit_ts_utc",
    "supersedes_seq",
]
AUDIT_COLUMNS = HASHED_COLUMNS + ["prev_hash", "row_hash"]

_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")

DDL = [
    "CREATE SCHEMA IF NOT EXISTS audit",
    """
    CREATE TABLE IF NOT EXISTS audit.audit_log (
        audit_seq      BIGINT PRIMARY KEY,
        table_name     VARCHAR NOT NULL,
        record_key     VARCHAR NOT NULL,
        action         VARCHAR NOT NULL CHECK (action IN ('INSERT', 'CORRECTION')),
        field          VARCHAR NOT NULL,
        old_value      VARCHAR,
        new_value      VARCHAR,
        performed_by   VARCHAR NOT NULL,
        reason         VARCHAR NOT NULL,
        audit_ts_utc   TIMESTAMP NOT NULL,
        supersedes_seq BIGINT,
        prev_hash      VARCHAR NOT NULL,
        row_hash       VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.chain_verify (
        verified_at       TIMESTAMP NOT NULL,
        ok                BOOLEAN NOT NULL,
        rows_checked      BIGINT NOT NULL,
        first_broken_seq  BIGINT,
        broken_table_name VARCHAR,
        broken_record_key VARCHAR,
        broken_check      VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit.file_integrity (
        file_name      VARCHAR NOT NULL,
        plate_id       VARCHAR,
        stored_sha256  VARCHAR,
        current_sha256 VARCHAR,
        matches        BOOLEAN NOT NULL,
        checked_at     TIMESTAMP NOT NULL
    )
    """,
    # Key columns of each audited table, so reconcile() can rebuild record_key from a live row.
    """
    CREATE TABLE IF NOT EXISTS audit.audited_tables (
        table_name    VARCHAR PRIMARY KEY,
        key_cols      VARCHAR NOT NULL,
        registered_at TIMESTAMP NOT NULL
    )
    """,
    # Append-only checkpoints: one per audited write, recording the chain head at that moment (BUG-004).
    """
    CREATE TABLE IF NOT EXISTS audit.chain_checkpoint (
        checkpoint_seq  BIGINT PRIMARY KEY,
        head_seq        BIGINT NOT NULL,
        head_hash       VARCHAR NOT NULL,
        head_table_name VARCHAR,
        head_record_key VARCHAR,
        created_at_utc  TIMESTAMP NOT NULL
    )
    """,
    # Base row vs audit trail reconciliation results (BUG-005). One issue='RUN' row marks each run.
    """
    CREATE TABLE IF NOT EXISTS audit.record_reconciliation (
        checked_at  TIMESTAMP NOT NULL,
        table_name  VARCHAR,
        key_type    VARCHAR,
        record_key  VARCHAR,
        issue       VARCHAR NOT NULL,
        audit_seq   BIGINT,
        detail      VARCHAR
    )
    """,
]


class AppendOnlyError(RuntimeError):
    """Raised for any attempt to change or remove an audited record (AC-3.2), or to overwrite one by re-inserting."""


@dataclass
class ChainResult:
    ok: bool
    rows_checked: int
    first_broken_seq: int | None = None
    broken_table_name: str | None = None
    broken_record_key: str | None = None
    check: str | None = None  # CHAIN, CHECKPOINT, ANCHOR or RECORD: which check failed first


# --------------------------------------------------------------------------------------------------------------------
# Canonical serialisation and hashing
# --------------------------------------------------------------------------------------------------------------------

def _jsonable(value: Any) -> Any:
    """Turn one cell value into a JSON-safe, deterministic Python value."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        if pd.isna(value):
            return None
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts.to_pydatetime().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_jsonable(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value if isinstance(value, (str, int)) else str(value)


def canonical_json(obj: dict) -> str:
    """JSON with sorted keys, no spaces, ISO timestamps, NaN/NaT as null. Stable across runs."""
    return json.dumps({k: _jsonable(v) for k, v in obj.items()}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def compute_row_hash(prev_hash: str, row: dict) -> str:
    content = canonical_json({c: row.get(c) for c in HASHED_COLUMNS})
    return hashlib.sha256(f"{prev_hash}|{content}".encode()).hexdigest()


def _utc_now() -> dt.datetime:
    # Naive UTC (DESIGN 3: TIMESTAMP in UTC with no time zone).
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _record_key(values) -> str:
    return "|".join("" if _jsonable(v) is None else str(_jsonable(v)) for v in values)


# --------------------------------------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------------------------------------

def init_audit(con) -> None:
    """Create schema ``audit`` and its tables (idempotent)."""
    for stmt in DDL:
        con.execute(stmt)


def _check_table_name(table: str) -> None:
    if not _TABLE_RE.match(table or ""):
        raise ValueError(f"table must be 'schema.table', got {table!r}")
    if table.split(".")[0].lower() == "audit":
        raise AppendOnlyError("insert_records cannot write to the audit schema itself")


def _require_text(name: str, value: str) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{name} is required (ALCOA+ Attributable: who and why)")


def _table_columns(con, table: str) -> list[str]:
    schema, name = table.split(".")
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = ? "
        "ORDER BY ordinal_position",
        [schema, name],
    ).fetchall()
    if not rows:
        raise ValueError(f"table {table} does not exist; create it (pipeline/schema.py) before inserting")
    return [r[0] for r in rows]


def _chain_tail(con) -> tuple[int, str]:
    row = con.execute(f"SELECT audit_seq, row_hash FROM {AUDIT_LOG} ORDER BY audit_seq DESC LIMIT 1").fetchone()
    return (0, GENESIS_HASH) if row is None else (int(row[0]), row[1])


def _append_audit_rows(con, rows: list[dict]) -> list[int]:
    """Number, chain and insert audit rows. Caller owns the transaction."""
    last_seq, prev_hash = _chain_tail(con)
    out = []
    for i, row in enumerate(rows, start=1):
        row["audit_seq"] = last_seq + i
        row["prev_hash"] = prev_hash
        row["row_hash"] = compute_row_hash(prev_hash, row)
        prev_hash = row["row_hash"]
        out.append(row)
    frame = pd.DataFrame(out, columns=AUDIT_COLUMNS).astype(object)
    frame = frame.where(frame.notna(), None)
    con.register("_audit_frame", frame)
    try:
        con.execute(
            f"""INSERT INTO {AUDIT_LOG} ({", ".join(AUDIT_COLUMNS)})
            SELECT CAST(audit_seq AS BIGINT), CAST(table_name AS VARCHAR), CAST(record_key AS VARCHAR),
                   CAST(action AS VARCHAR), CAST(field AS VARCHAR), CAST(old_value AS VARCHAR),
                   CAST(new_value AS VARCHAR), CAST(performed_by AS VARCHAR), CAST(reason AS VARCHAR),
                   CAST(audit_ts_utc AS TIMESTAMP), CAST(supersedes_seq AS BIGINT),
                   CAST(prev_hash AS VARCHAR), CAST(row_hash AS VARCHAR)
            FROM _audit_frame ORDER BY audit_seq"""
        )
    finally:
        con.unregister("_audit_frame")
    head = out[-1]
    con.execute(
        "INSERT INTO audit.chain_checkpoint SELECT coalesce(max(checkpoint_seq), 0) + 1, ?, ?, ?, ?, ? "
        "FROM audit.chain_checkpoint",
        [head["audit_seq"], head["row_hash"], head["table_name"], head["record_key"], _utc_now()],
    )
    return [r["audit_seq"] for r in out]


def _register_table(con, table: str, key_cols: list[str]) -> None:
    """Remember a table's key columns (first insert). A later insert with different keys is refused."""
    joined = ",".join(key_cols)
    row = con.execute("SELECT key_cols FROM audit.audited_tables WHERE table_name = ?", [table]).fetchone()
    if row is None:
        con.execute("INSERT INTO audit.audited_tables VALUES (?, ?, ?)", [table, joined, _utc_now()])
    elif row[0] != joined:
        raise ValueError(f"{table} was registered with key_cols {row[0]!r}, not {joined!r}")


def _rows_as_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def insert_records(con, table: str, df: pd.DataFrame, key_cols: list[str], performed_by: str, reason: str) -> int:
    """Insert ``df`` into ``table`` and write one INSERT audit row per record, in one transaction.

    * ``table`` is ``schema.table`` and must already exist (DDL is owned by pipeline/schema.py).
    * ``key_cols`` identify a record; ``record_key`` is their values joined with ``|``. Keys must be non-null and unique
      within ``df`` and must not already exist in ``table`` (no silent overwrite: use ``correct_record``).
    * The audit row's ``new_value`` is the canonical JSON of the full record AS STORED (read back from ``table`` after
      the insert, every column, with the table's types), so ``reconcile`` can later compare it with the live row.
      ``old_value`` is null; ``field`` is ``*``.

    Returns the number of rows inserted. If anything fails, neither the data nor the audit rows are written.
    """
    _check_table_name(table)
    _require_text("performed_by", performed_by)
    _require_text("reason", reason)
    if not key_cols:
        raise ValueError("key_cols must name at least one column")
    missing = [c for c in key_cols if c not in df.columns]
    if missing:
        raise ValueError(f"key columns not in dataframe: {missing}")
    if df.empty:
        return 0
    if df[key_cols].isna().any().any():
        raise ValueError(f"null values in key columns {key_cols} for {table}")
    keys = [_record_key(v) for v in df[key_cols].itertuples(index=False, name=None)]
    dupes = pd.Series(keys)[pd.Series(keys).duplicated()].unique().tolist()
    if dupes:
        raise AppendOnlyError(f"duplicate keys within batch for {table}: {dupes[:5]}")

    table_cols = _table_columns(con, table)
    extra = [c for c in df.columns if c not in table_cols]
    if extra:
        raise ValueError(f"columns {extra} are not in {table}")

    data = df.reset_index(drop=True)
    con.register("_ins_frame", data)
    try:
        key_match = " AND ".join(f't."{c}" = f."{c}"' for c in key_cols)
        select_keys = ", ".join(f'f."{c}"' for c in key_cols)
        clash = con.execute(
            f"SELECT {select_keys} "
            f"FROM _ins_frame f JOIN {table} t ON {key_match} LIMIT 5"
        ).fetchall()
        if clash:
            raise AppendOnlyError(
                f"records already exist in {table} for keys {[_record_key(r) for r in clash]}; "
                "re-inserting would overwrite them. Use correct_record()."
            )

        ts = _utc_now()
        cols = ", ".join(f'"{c}"' for c in data.columns)
        con.begin()
        try:
            _register_table(con, table, key_cols)
            con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _ins_frame")
            stored = _rows_as_dicts(con.execute(
                f"SELECT t.* FROM {table} t WHERE EXISTS (SELECT 1 FROM _ins_frame f WHERE {key_match})"))
            by_key = {_record_key([r[c] for c in key_cols]): r for r in stored}
            if len(by_key) != len(keys) or set(by_key) != set(keys):
                raise AppendOnlyError(f"read-back of {table} does not match the inserted keys")
            records = [by_key[k] for k in keys]
            audit_rows = [
                {
                    "table_name": table,
                    "record_key": key,
                    "action": "INSERT",
                    "field": "*",
                    "old_value": None,
                    "new_value": canonical_json(rec),
                    "performed_by": performed_by,
                    "reason": reason,
                    "audit_ts_utc": ts,
                    "supersedes_seq": None,
                }
                for key, rec in zip(keys, records, strict=True)
            ]
            _append_audit_rows(con, audit_rows)
            con.commit()
        except Exception:
            con.rollback()
            raise
    finally:
        con.unregister("_ins_frame")
    return len(data)


def correct_record(con, table: str, key: dict, field: str, new_value, performed_by: str, reason: str) -> int:
    """Record a correction to one field of one record as a NEW audit row (never an UPDATE).

    ``key`` maps key column -> value, in the same order as the ``key_cols`` used at insert. The CORRECTION row's
    ``supersedes_seq`` points to the audit row it replaces: the latest earlier correction of the same field, or else
    the record's INSERT row. ``old_value`` is the value being replaced. Values are stored as canonical JSON scalars.
    v1 keeps base tables insert-only, so the audit_log is the record of corrections (DESIGN 4).

    Returns the new audit_seq.
    """
    _check_table_name(table)
    _require_text("performed_by", performed_by)
    _require_text("reason", reason)
    if not key:
        raise ValueError("key must not be empty")
    cols = _table_columns(con, table)
    if field not in cols:
        raise ValueError(f"field {field!r} is not a column of {table}")
    if field in key:
        raise AppendOnlyError("key fields cannot be corrected; they identify the record")
    record_key = _record_key(key.values())

    prior = con.execute(
        f"""SELECT audit_seq, action, field, new_value FROM {AUDIT_LOG}
            WHERE table_name = ? AND record_key = ?
              AND (action = 'INSERT' OR (action = 'CORRECTION' AND field = ?))
            ORDER BY audit_seq DESC""",
        [table, record_key, field],
    ).fetchall()
    if not prior:
        raise KeyError(f"no audited record {record_key!r} in {table}")
    latest = prior[0]
    if latest[1] == "CORRECTION":
        old_value = latest[3]
    else:
        inserted = json.loads(latest[3]) if latest[3] else {}
        old_value = json.dumps(inserted.get(field), sort_keys=True, ensure_ascii=False)
    new_json = json.dumps(_jsonable(new_value), sort_keys=True, ensure_ascii=False)

    row = {
        "table_name": table,
        "record_key": record_key,
        "action": "CORRECTION",
        "field": field,
        "old_value": old_value,
        "new_value": new_json,
        "performed_by": performed_by,
        "reason": reason,
        "audit_ts_utc": _utc_now(),
        "supersedes_seq": int(latest[0]),
    }
    con.begin()
    try:
        (seq,) = _append_audit_rows(con, [row])
        con.commit()
    except Exception:
        con.rollback()
        raise
    return seq


def update(*args, **kwargs) -> NoReturn:
    """There is no update path. Use correct_record() to append a correction (AC-3.2)."""
    raise AppendOnlyError("UPDATE is not allowed on audited records; use correct_record() to append a correction")


def delete(*args, **kwargs) -> NoReturn:
    """There is no delete path (AC-3.2)."""
    raise AppendOnlyError("DELETE is not allowed on audited records; the audit trail is append-only")


def reconcile(con) -> list[dict]:
    """Compare every live row of every audited table with its INSERT audit row (BUG-005, REVIEW F1).

    Base tables are insert-only in v1 (corrections live in the audit_log and never change the base row), so a live
    row must equal the canonical JSON stored at insert. Returns one dict per problem, sorted by audit_seq:

    * ``RECORD_MODIFIED``  the row exists but differs from its audit payload (detail lists field: audit -> live)
    * ``RECORD_DELETED``   the audit_log has an INSERT but the row is gone
    * ``RECORD_UNAUDITED`` a live row has no INSERT audit row (inserted by direct SQL), or repeats a key
    """
    issues: list[dict] = []
    tables = con.execute("SELECT table_name, key_cols FROM audit.audited_tables ORDER BY table_name").fetchall()
    for table, key_cols_s in tables:
        key_cols = key_cols_s.split(",")
        key_type = "|".join(key_cols)
        expected = {
            r[0]: (int(r[1]), r[2])
            for r in con.execute(
                f"SELECT record_key, audit_seq, new_value FROM {AUDIT_LOG} WHERE table_name = ? AND action = 'INSERT'",
                [table],
            ).fetchall()
        }
        try:
            live = _rows_as_dicts(con.execute(f"SELECT * FROM {table}"))
        except Exception as exc:  # table dropped or renamed
            issues.append({"table_name": table, "key_type": key_type, "record_key": None, "issue": "RECORD_DELETED",
                           "audit_seq": min((v[0] for v in expected.values()), default=None),
                           "detail": f"table unreadable: {exc}"[:300]})
            continue
        seen: set[str] = set()
        for row in live:
            key = _record_key([row[c] for c in key_cols])
            base = {"table_name": table, "key_type": key_type, "record_key": key}
            if key in seen or key not in expected:
                issues.append({**base, "issue": "RECORD_UNAUDITED", "audit_seq": None,
                               "detail": "duplicate key" if key in seen else "row has no INSERT audit row"})
                seen.add(key)
                continue
            seen.add(key)
            seq, payload = expected[key]
            current = canonical_json(row)
            if current != payload:
                was, now = json.loads(payload), json.loads(current)
                diffs = [f"{f}: {json.dumps(was.get(f))} -> {json.dumps(now.get(f))}"
                         for f in sorted(set(was) | set(now)) if was.get(f) != now.get(f)]
                issues.append({**base, "issue": "RECORD_MODIFIED", "audit_seq": seq, "detail": "; ".join(diffs)[:500]})
        for key, (seq, _) in expected.items():
            if key not in seen:
                issues.append({"table_name": table, "key_type": key_type, "record_key": key,
                               "issue": "RECORD_DELETED", "audit_seq": seq, "detail": "audited row is missing"})
    issues.sort(key=lambda r: (r["audit_seq"] is None, r["audit_seq"] or 0, r["table_name"], r["record_key"] or ""))
    return issues


def _load_anchor(anchor) -> dict:
    if isinstance(anchor, dict):
        return anchor
    from pathlib import Path

    return json.loads(Path(anchor).read_text(encoding="utf-8"))


def verify_chain(con, anchor=None, records: bool = True) -> ChainResult:
    """Verify the audit trail and report the first problem found. Checks run in this order:

    1. ``CHAIN``: recompute the hash chain in audit_seq order. A row is broken if its audit_seq is not the next
       integer (gap or reorder), its prev_hash is not the previous row's row_hash, or its row_hash does not match its
       own content. A direct edit of row k (INJ-7) gives ``first_broken_seq == k``.
    2. ``CHECKPOINT``: every ``audit.chain_checkpoint`` row must still match the row hash at its head_seq, checkpoint
       numbers must be gap-free, and the newest checkpoint must be the chain head. This catches deleting or
       re-hashing the newest rows (BUG-004), unless the forger rewrites the checkpoints too.
    3. ``ANCHOR`` (only if ``anchor`` is given: a dict, or the path of the JSON written by
       ``pipeline.integrity.write_chain_anchor``): the row at the anchored head_seq must exist with the anchored
       hash. This external control survives a forger who also rewrites the checkpoints.
    4. ``RECORD`` (if ``records``): ``reconcile`` finds no live base row that differs from the audit trail (BUG-005).
    """
    cur = con.execute(f"SELECT {', '.join(AUDIT_COLUMNS)} FROM {AUDIT_LOG} ORDER BY audit_seq")
    prev_hash = GENESIS_HASH
    expected_seq = 1
    checked = 0
    hashes: dict[int, str] = {}
    last_row: dict | None = None
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        for values in batch:
            row = dict(zip(AUDIT_COLUMNS, values, strict=True))
            checked += 1
            broken = (
                row["audit_seq"] != expected_seq
                or row["prev_hash"] != prev_hash
                or compute_row_hash(prev_hash, row) != row["row_hash"]
            )
            if broken:
                return ChainResult(False, checked, int(row["audit_seq"]), row["table_name"], row["record_key"],
                                   "CHAIN")
            hashes[row["audit_seq"]] = row["row_hash"]
            prev_hash = row["row_hash"]
            expected_seq += 1
            last_row = row

    # 2. in-database checkpoints
    cps = con.execute(
        "SELECT checkpoint_seq, head_seq, head_hash, head_table_name, head_record_key "
        "FROM audit.chain_checkpoint ORDER BY checkpoint_seq"
    ).fetchall()
    if last_row is not None and not cps:
        return ChainResult(False, checked, 1, last_row["table_name"], last_row["record_key"], "CHECKPOINT")
    for i, (cp_seq, head_seq, head_hash, t, k) in enumerate(cps, start=1):
        if cp_seq != i or hashes.get(head_seq) != head_hash:
            return ChainResult(False, checked, int(head_seq), t, k, "CHECKPOINT")
    if cps and cps[-1][1] != checked:
        # audit rows appended after the newest checkpoint, i.e. outside the API
        nxt = cps[-1][1] + 1
        row = con.execute(f"SELECT table_name, record_key FROM {AUDIT_LOG} WHERE audit_seq = ?", [nxt]).fetchone()
        return ChainResult(False, checked, nxt, row[0] if row else None, row[1] if row else None, "CHECKPOINT")

    # 3. external anchor
    if anchor is not None:
        a = _load_anchor(anchor)
        head_seq = int(a["head_seq"])
        if hashes.get(head_seq) != a["head_hash"]:
            return ChainResult(False, checked, head_seq, a.get("head_table_name"), a.get("head_record_key"),
                               "ANCHOR")

    # 4. live base rows vs the audit trail
    if records:
        issues = reconcile(con)
        if issues:
            first = issues[0]
            return ChainResult(False, checked, first["audit_seq"], first["table_name"], first["record_key"],
                               "RECORD")
    return ChainResult(True, checked)
