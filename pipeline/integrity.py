"""Integrity checks written to the audit schema (owner: GxP seat).

* ``write_chain_verify``: stores a ``verify_chain`` result in ``audit.chain_verify`` (AC-3.3).
* ``rehash_raw_files``: re-hashes every raw plate file recorded in ``lims.raw_files`` and stores the comparison in
  ``audit.file_integrity`` (AC-3.4 Original, AC-3.5). ``integrity.alcoa_findings`` turns mismatches into HASH_MISMATCH.
* ``reconcile_records``: compares every live base-table row with its INSERT audit row and stores the problems in
  ``audit.record_reconciliation`` (BUG-005). ``integrity.alcoa_findings`` turns them into RECORD_MISMATCH.
* ``write_chain_anchor``: writes the chain head to a write-once, read-only JSON file OUTSIDE the database, which
  ``verify_chain(con, anchor=path)`` checks later (BUG-004).

These tables hold check results, not GxP records, so they are written directly (not through insert_records). Each
row carries its check timestamp, and dbt reads the latest check per file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
from pathlib import Path

import pandas as pd

from pipeline.audit import AUDIT_LOG, ChainResult, init_audit, reconcile


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def sha256_file(path: Path, chunk: int = 1 << 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_chain_verify(con, result: ChainResult) -> None:
    init_audit(con)
    con.execute(
        "INSERT INTO audit.chain_verify (verified_at, ok, rows_checked, first_broken_seq, broken_table_name, "
        "broken_record_key, broken_check) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [_utc_now(), bool(result.ok), int(result.rows_checked), result.first_broken_seq, result.broken_table_name,
         result.broken_record_key, result.check],
    )


def rehash_raw_files(con, raw_dir: Path) -> int:
    """Re-hash each file in ``lims.raw_files`` (looked up as ``raw_dir / file_name``). Returns the mismatch count.

    A missing file counts as a mismatch with ``current_sha256`` null.
    """
    init_audit(con)
    stored = con.execute("SELECT file_name, plate_id, sha256 FROM lims.raw_files ORDER BY file_name").fetchall()
    now = _utc_now()
    rows = []
    for file_name, plate_id, stored_sha in stored:
        path = Path(raw_dir) / file_name
        current = sha256_file(path) if path.is_file() else None
        rows.append({
            "file_name": file_name,
            "plate_id": plate_id,
            "stored_sha256": stored_sha,
            "current_sha256": current,
            "matches": current is not None and current == stored_sha,
            "checked_at": now,
        })
    if rows:
        frame = pd.DataFrame(rows)
        con.register("_fi_frame", frame)
        try:
            con.execute(
                "INSERT INTO audit.file_integrity (file_name, plate_id, stored_sha256, current_sha256, matches, "
                "checked_at) SELECT file_name, plate_id, stored_sha256, current_sha256, matches, checked_at "
                "FROM _fi_frame"
            )
        finally:
            con.unregister("_fi_frame")
    return sum(not r["matches"] for r in rows)


def reconcile_records(con) -> int:
    """Run ``audit.reconcile`` and store the result in ``audit.record_reconciliation``. Returns the issue count.

    Each run writes one ``issue = 'RUN'`` marker row plus one row per problem, all with the same ``checked_at``, so
    dbt can read the latest run even when it found nothing.
    """
    init_audit(con)
    now = _utc_now()
    issues = reconcile(con)
    rows = [[now, None, None, None, "RUN", None, f"{len(issues)} issue(s)"]]
    rows += [[now, i["table_name"], i["key_type"], i["record_key"], i["issue"], i["audit_seq"], i["detail"]]
             for i in issues]
    con.executemany("INSERT INTO audit.record_reconciliation VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return len(issues)


def write_chain_anchor(con, path: Path) -> dict:
    """Write the current chain head to ``path`` as JSON, once, and make the file read-only (BUG-004).

    The file is the external anchor: keep it outside the database (and ideally off the machine, e.g. committed to git
    or sent to a reviewer). Raises ``FileExistsError`` rather than overwrite an existing anchor.
    """
    row = con.execute(
        f"SELECT audit_seq, row_hash, table_name, record_key FROM {AUDIT_LOG} ORDER BY audit_seq DESC LIMIT 1"
    ).fetchone()
    anchor = {
        "head_seq": int(row[0]) if row else 0,
        "head_hash": row[1] if row else "0" * 64,
        "head_table_name": row[2] if row else None,
        "head_record_key": row[3] if row else None,
        "written_at_utc": _utc_now().isoformat(),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as f:  # "x": never overwrite
        json.dump(anchor, f, indent=2, sort_keys=True)
        f.write("\n")
    os.chmod(path, stat.S_IREAD)
    return anchor
