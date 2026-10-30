"""GXP-01 unit tests: append-only audit API and hash chain (AC-3.1, AC-3.2, AC-3.3). In-memory DuckDB, no build."""

import json

import duckdb
import pandas as pd
import pytest

from pipeline import audit
from pipeline.audit import AppendOnlyError


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    audit.init_audit(c)
    c.execute("CREATE SCHEMA lims")
    c.execute(
        "CREATE TABLE lims.samples (sample_id VARCHAR, subject_id VARCHAR, visit VARCHAR, collected_at TIMESTAMP)"
    )
    c.execute("CREATE TABLE lims.custody_events (event_id VARCHAR, sample_id VARCHAR, step VARCHAR, "
              "performed_by VARCHAR, performed_at TIMESTAMP, recorded_at TIMESTAMP, location VARCHAR)")
    yield c
    c.close()


def _samples(n=3, start=1):
    return pd.DataFrame({
        "sample_id": [f"SMP-{i:05d}" for i in range(start, start + n)],
        "subject_id": [f"SUBJ-{i:04d}" for i in range(start, start + n)],
        "visit": ["D1"] * n,
        "collected_at": pd.to_datetime(["2026-01-05 09:00:00"] * n),
    })


def _events(n=4):
    return pd.DataFrame({
        "event_id": [f"EVT-{i:06d}" for i in range(1, n + 1)],
        "sample_id": ["SMP-00001"] * n,
        "step": ["collected", "received", "aliquoted", "stored"][:n],
        "performed_by": ["USR-01"] * n,
        "performed_at": pd.date_range("2026-01-05 09:00", periods=n, freq="h"),
        "recorded_at": pd.date_range("2026-01-05 09:05", periods=n, freq="h"),
        "location": ["SITE-01"] * n,
    })


def test_insert_writes_data_and_one_audit_row_per_record(con):
    n = audit.insert_records(con, "lims.samples", _samples(3), ["sample_id"], "USR-01", "initial LIMS load")
    assert n == 3
    assert con.execute("SELECT count(*) FROM lims.samples").fetchone()[0] == 3
    rows = con.execute(
        "SELECT audit_seq, table_name, record_key, action, field, old_value, new_value, performed_by, reason, "
        "audit_ts_utc FROM audit.audit_log ORDER BY audit_seq"
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2, 3]
    assert {r[1] for r in rows} == {"lims.samples"}
    assert [r[2] for r in rows] == ["SMP-00001", "SMP-00002", "SMP-00003"]
    assert all(r[3] == "INSERT" and r[4] == "*" and r[5] is None for r in rows)
    assert all(r[7] == "USR-01" and r[8] == "initial LIMS load" and r[9] is not None for r in rows)
    first = json.loads(rows[0][6])
    assert first == {"sample_id": "SMP-00001", "subject_id": "SUBJ-0001", "visit": "D1",
                     "collected_at": "2026-01-05T09:00:00"}


def test_audit_seq_is_gap_free_across_tables(con):
    audit.insert_records(con, "lims.samples", _samples(2), ["sample_id"], "USR-01", "load")
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-02", "load")
    seqs = [r[0] for r in con.execute("SELECT audit_seq FROM audit.audit_log ORDER BY 1").fetchall()]
    assert seqs == list(range(1, 7))


def test_composite_key_joined_with_pipe(con):
    con.execute("CREATE SCHEMA assay")
    con.execute("CREATE TABLE assay.well_reads (plate_id VARCHAR, well VARCHAR, od DOUBLE)")
    df = pd.DataFrame({"plate_id": ["PLATE-001", "PLATE-001"], "well": ["A1", "A2"], "od": [1.234, float("nan")]})
    audit.insert_records(con, "assay.well_reads", df, ["plate_id", "well"], "USR-03", "ingest")
    keys = [r[0] for r in con.execute("SELECT record_key FROM audit.audit_log ORDER BY audit_seq").fetchall()]
    assert keys == ["PLATE-001|A1", "PLATE-001|A2"]
    nv = json.loads(con.execute("SELECT new_value FROM audit.audit_log WHERE audit_seq = 2").fetchone()[0])
    assert nv["od"] is None  # NaN serialised as null, not as invalid JSON


def test_empty_frame_inserts_nothing(con):
    assert audit.insert_records(con, "lims.samples", _samples(0), ["sample_id"], "USR-01", "load") == 0
    assert con.execute("SELECT count(*) FROM audit.audit_log").fetchone()[0] == 0


def test_reinsert_same_key_is_refused_no_silent_overwrite(con):
    audit.insert_records(con, "lims.samples", _samples(2), ["sample_id"], "USR-01", "load")
    with pytest.raises(AppendOnlyError):
        audit.insert_records(con, "lims.samples", _samples(1), ["sample_id"], "USR-01", "load again")
    assert con.execute("SELECT count(*) FROM lims.samples").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM audit.audit_log").fetchone()[0] == 2


def test_duplicate_keys_within_batch_refused(con):
    df = pd.concat([_samples(1), _samples(1)])
    with pytest.raises(AppendOnlyError):
        audit.insert_records(con, "lims.samples", df, ["sample_id"], "USR-01", "load")
    assert con.execute("SELECT count(*) FROM lims.samples").fetchone()[0] == 0


@pytest.mark.parametrize("who,why", [("", "load"), ("USR-01", ""), (None, "load"), ("USR-01", "   ")])
def test_who_and_why_are_required(con, who, why):
    with pytest.raises(ValueError):
        audit.insert_records(con, "lims.samples", _samples(1), ["sample_id"], who, why)


def test_failed_batch_rolls_back_data_and_audit(con):
    bad = _samples(2)
    bad["collected_at"] = ["2026-01-05 09:00:00", "not a timestamp"]
    with pytest.raises(duckdb.Error):
        audit.insert_records(con, "lims.samples", bad, ["sample_id"], "USR-01", "load")
    assert con.execute("SELECT count(*) FROM lims.samples").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM audit.audit_log").fetchone()[0] == 0


def test_audit_failure_rolls_back_the_data_insert(con, monkeypatch):
    """Data and audit rows are one transaction: if the audit write fails, the data insert is undone too."""
    def boom(*a, **k):
        raise RuntimeError("audit write failed")
    monkeypatch.setattr(audit, "_append_audit_rows", boom)
    with pytest.raises(RuntimeError):
        audit.insert_records(con, "lims.samples", _samples(2), ["sample_id"], "USR-01", "load")
    assert con.execute("SELECT count(*) FROM lims.samples").fetchone()[0] == 0


def test_cannot_write_audit_schema_or_missing_table(con):
    with pytest.raises(AppendOnlyError):
        audit.insert_records(con, "audit.audit_log", _samples(1), ["sample_id"], "USR-01", "x")
    with pytest.raises(ValueError):
        audit.insert_records(con, "lims.nope", _samples(1), ["sample_id"], "USR-01", "x")
    with pytest.raises(ValueError):
        audit.insert_records(con, "lims.samples; DROP TABLE x", _samples(1), ["sample_id"], "USR-01", "x")


def test_update_and_delete_always_raise(con):
    """AC-3.2: the write API has no update or delete path."""
    with pytest.raises(AppendOnlyError):
        audit.update(con, "audit.audit_log", {"audit_seq": 1}, "new_value", "x")
    with pytest.raises(AppendOnlyError):
        audit.delete(con, "lims.samples", {"sample_id": "SMP-00001"})
    public = {n for n in dir(audit) if not n.startswith("_") and callable(getattr(audit, n))}
    assert not {n for n in public if n.lower().startswith(("upd", "del", "remove", "overwrite", "upsert"))} - {
        "update", "delete"}


def test_clean_chain_verifies(con):
    audit.insert_records(con, "lims.samples", _samples(5), ["sample_id"], "USR-01", "load")
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-01", "load")
    res = audit.verify_chain(con)
    assert res.ok and res.rows_checked == 9 and res.first_broken_seq is None
    first = con.execute("SELECT prev_hash FROM audit.audit_log WHERE audit_seq = 1").fetchone()[0]
    assert first == "0" * 64


def test_empty_chain_verifies(con):
    res = audit.verify_chain(con)
    assert res.ok and res.rows_checked == 0


@pytest.mark.parametrize("k", [1, 4, 9])
def test_direct_sql_update_breaks_chain_at_that_row(con, k):
    """AC-3.3: a direct UPDATE of row k (bypassing the API) is detected at exactly row k."""
    audit.insert_records(con, "lims.samples", _samples(5), ["sample_id"], "USR-01", "load")
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-01", "load")
    expected_key = con.execute("SELECT record_key FROM audit.audit_log WHERE audit_seq = ?", [k]).fetchone()[0]
    con.execute("UPDATE audit.audit_log SET performed_by = 'USR-99' WHERE audit_seq = ?", [k])
    res = audit.verify_chain(con)
    assert not res.ok
    assert res.first_broken_seq == k
    assert res.broken_record_key == expected_key


def test_deleted_row_breaks_chain(con):
    audit.insert_records(con, "lims.samples", _samples(5), ["sample_id"], "USR-01", "load")
    con.execute("DELETE FROM audit.audit_log WHERE audit_seq = 3")
    res = audit.verify_chain(con)
    assert not res.ok and res.first_broken_seq == 4  # row 4 is where the gap shows


def test_rehashed_forgery_still_breaks_at_next_row(con):
    """Even if a tamperer recomputes row k's own hash, row k+1's prev_hash no longer links."""
    audit.insert_records(con, "lims.samples", _samples(4), ["sample_id"], "USR-01", "load")
    row = dict(zip(audit.AUDIT_COLUMNS, con.execute(
        f"SELECT {', '.join(audit.AUDIT_COLUMNS)} FROM audit.audit_log WHERE audit_seq = 2").fetchone(), strict=True))
    row["reason"] = "forged"
    forged = audit.compute_row_hash(row["prev_hash"], row)
    con.execute("UPDATE audit.audit_log SET reason = 'forged', row_hash = ? WHERE audit_seq = 2", [forged])
    res = audit.verify_chain(con)
    assert not res.ok and res.first_broken_seq == 3


def test_correction_appends_row_pointing_to_superseded_row(con):
    """AC-3.2: corrections are new rows that point to the record they replace; the base table is untouched."""
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-01", "load")
    insert_seq = con.execute(
        "SELECT audit_seq FROM audit.audit_log WHERE record_key = 'EVT-000002'").fetchone()[0]
    seq1 = audit.correct_record(con, "lims.custody_events", {"event_id": "EVT-000002"}, "location", "FRZ-02",
                                "USR-02", "freezer mislabelled at entry")
    seq2 = audit.correct_record(con, "lims.custody_events", {"event_id": "EVT-000002"}, "location", "FRZ-03",
                                "USR-03", "second correction")
    r1 = con.execute("SELECT action, field, old_value, new_value, supersedes_seq, performed_by, reason "
                     "FROM audit.audit_log WHERE audit_seq = ?", [seq1]).fetchone()
    r2 = con.execute("SELECT old_value, new_value, supersedes_seq FROM audit.audit_log WHERE audit_seq = ?",
                     [seq2]).fetchone()
    assert r1 == ("CORRECTION", "location", '"SITE-01"', '"FRZ-02"', insert_seq, "USR-02",
                  "freezer mislabelled at entry")
    assert r2 == ('"FRZ-02"', '"FRZ-03"', seq1)
    # base table is insert-only: original value still there, no UPDATE happened
    assert con.execute("SELECT location FROM lims.custody_events WHERE event_id = 'EVT-000002'").fetchone()[0] \
        == "SITE-01"
    assert audit.verify_chain(con).ok


def test_correction_validation(con):
    audit.insert_records(con, "lims.samples", _samples(1), ["sample_id"], "USR-01", "load")
    with pytest.raises(KeyError):
        audit.correct_record(con, "lims.samples", {"sample_id": "SMP-99999"}, "visit", "D29", "USR-01", "x")
    with pytest.raises(ValueError):
        audit.correct_record(con, "lims.samples", {"sample_id": "SMP-00001"}, "no_such", "D29", "USR-01", "x")
    with pytest.raises(AppendOnlyError):
        audit.correct_record(con, "lims.samples", {"sample_id": "SMP-00001"}, "sample_id", "SMP-2", "USR-01", "x")
    with pytest.raises(ValueError):
        audit.correct_record(con, "lims.samples", {"sample_id": "SMP-00001"}, "visit", "D29", "USR-01", "")


def test_hash_is_deterministic_and_content_sensitive():
    row = {c: None for c in audit.HASHED_COLUMNS}
    row.update(audit_seq=1, table_name="lims.samples", record_key="SMP-00001", action="INSERT", field="*",
               performed_by="USR-01", reason="load")
    h1 = audit.compute_row_hash("0" * 64, row)
    assert h1 == audit.compute_row_hash("0" * 64, dict(row)) and len(h1) == 64
    assert h1 != audit.compute_row_hash("0" * 64, {**row, "reason": "load "})
    assert h1 != audit.compute_row_hash("1" * 64, row)


# ---------------------------------------------------------------------------------------------------------------------
# GXP-03: INJ-7 tamper is caught at the right record (AC-3.3) and the result is stored in audit.chain_verify
# ---------------------------------------------------------------------------------------------------------------------

def test_tamper_then_verify_names_the_tampered_event(con):
    from generator.tamper import tamper_audit_row
    from pipeline.integrity import write_chain_verify

    audit.insert_records(con, "lims.samples", _samples(3), ["sample_id"], "USR-01", "load")
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-01", "load")
    write_chain_verify(con, audit.verify_chain(con))

    seq = tamper_audit_row(con, "EVT-000003")
    assert seq == 3 + 3  # 3 sample rows, then EVT-000003 is the 3rd event row
    nv = json.loads(con.execute("SELECT new_value FROM audit.audit_log WHERE audit_seq = ?", [seq]).fetchone()[0])
    assert nv["performed_at"] == "2026-01-04T11:00:00"  # back-dated one day

    res = audit.verify_chain(con)
    assert (res.ok, res.first_broken_seq, res.broken_table_name, res.broken_record_key) == (
        False, seq, "lims.custody_events", "EVT-000003")
    write_chain_verify(con, res)
    stored = con.execute("SELECT ok, first_broken_seq, broken_record_key FROM audit.chain_verify "
                         "ORDER BY verified_at, ok DESC").fetchall()
    assert stored[0] == (True, None, None)
    assert stored[-1] == (False, seq, "EVT-000003")


def test_tamper_unknown_event_raises(con):
    from generator.tamper import tamper_audit_row
    with pytest.raises(KeyError):
        tamper_audit_row(con, "EVT-999999")


# ---------------------------------------------------------------------------------------------------------------------
# Full-build checks (GXP-06 / AC-3.1, AC-3.3). They skip until DE-09 provides the `built` fixtures.
# ---------------------------------------------------------------------------------------------------------------------

UNAUDITED = {"assay.ingest_errors"}  # DESIGN 3.2: holds no result


def _built(request, name):
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        pytest.skip(f"`{name}` fixture not available yet (DE-09)")


def test_every_base_table_row_has_an_insert_audit_row(request):
    """GXP-06: audit INSERT rows per table == that table's row count, for every lims.* and assay.* table."""
    con = _built(request, "built")["con"]
    tables = [f"{s}.{t}" for s, t in con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('lims', 'assay') AND table_type = 'BASE TABLE' ORDER BY 1, 2").fetchall()]
    audited = dict(con.execute(
        "SELECT table_name, count(*) FROM audit.audit_log WHERE action = 'INSERT' GROUP BY 1").fetchall())
    mismatches = {}
    for t in tables:
        if t in UNAUDITED:
            continue
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        if audited.get(t, 0) != n:
            mismatches[t] = (n, audited.get(t, 0))
    assert not mismatches, f"table: (rows, audit INSERT rows) {mismatches}"


def test_chain_broken_exactly_at_inj7_on_build(request):
    b = _built(request, "built")
    con, truth = b["con"], b["truth"]
    inj7 = set(truth.loc[truth["inj_type"] == "INJ-7", "affected_key"])
    assert len(inj7) == 1
    ok, key = con.execute("SELECT ok, broken_record_key FROM audit.chain_verify ORDER BY verified_at DESC LIMIT 1"
                          ).fetchone()
    assert not ok and key in inj7


def test_chain_ok_on_clean_build(request):
    con = _built(request, "clean_built")["con"]
    ok, n = con.execute("SELECT ok, rows_checked FROM audit.chain_verify ORDER BY verified_at DESC LIMIT 1").fetchone()
    assert ok and n > 0


# ---------------------------------------------------------------------------------------------------------------------
# BUG-005 (REVIEW F1): live base rows are reconciled with the audit trail
# ---------------------------------------------------------------------------------------------------------------------

def _load_both(con):
    con.execute("CREATE TABLE lims.users (user_id VARCHAR, display_name VARCHAR)")
    audit.insert_records(con, "lims.users", pd.DataFrame({"user_id": ["USR-01", "USR-02"],
                                                          "display_name": ["Lab Tech 01", "Lab Tech 02"]}),
                         ["user_id"], "USR-01", "load")
    audit.insert_records(con, "lims.samples", _samples(3), ["sample_id"], "USR-01", "load")
    audit.insert_records(con, "lims.custody_events", _events(4), ["event_id"], "USR-01", "load")


def test_clean_load_reconciles(con):
    _load_both(con)
    assert audit.reconcile(con) == []
    assert audit.verify_chain(con).ok


def test_audit_payload_is_the_stored_row(con):
    """new_value is read back from the table, so string input is stored with the table's types."""
    df = _samples(1)
    df["collected_at"] = ["2026-01-05 09:00:00"]  # string in, TIMESTAMP stored
    audit.insert_records(con, "lims.samples", df, ["sample_id"], "USR-01", "load")
    nv = json.loads(con.execute("SELECT new_value FROM audit.audit_log").fetchone()[0])
    assert nv["collected_at"] == "2026-01-05T09:00:00"
    assert audit.reconcile(con) == []


def test_base_row_edit_is_found_with_field_diff(con):
    _load_both(con)
    seq = con.execute("SELECT audit_seq FROM audit.audit_log WHERE record_key = 'EVT-000003'").fetchone()[0]
    con.execute("UPDATE lims.custody_events SET performed_by = 'USR-02' WHERE event_id = 'EVT-000003'")
    issues = audit.reconcile(con)
    assert [(i["issue"], i["table_name"], i["key_type"], i["record_key"], i["audit_seq"]) for i in issues] == [
        ("RECORD_MODIFIED", "lims.custody_events", "event_id", "EVT-000003", seq)]
    assert issues[0]["detail"] == 'performed_by: "USR-01" -> "USR-02"'
    res = audit.verify_chain(con)
    assert (res.ok, res.check, res.first_broken_seq, res.broken_record_key) == (False, "RECORD", seq, "EVT-000003")


def test_base_row_delete_and_direct_insert_are_found(con):
    _load_both(con)
    con.execute("DELETE FROM lims.samples WHERE sample_id = 'SMP-00002'")
    con.execute("INSERT INTO lims.samples VALUES ('SMP-09999', 'SUBJ-0001', 'D1', '2026-01-05 09:00:00')")
    con.execute("INSERT INTO lims.samples VALUES ('SMP-00001', 'SUBJ-0001', 'D1', '2026-01-05 09:00:00')")
    got = {(i["issue"], i["record_key"]) for i in audit.reconcile(con)}
    assert got == {("RECORD_DELETED", "SMP-00002"), ("RECORD_UNAUDITED", "SMP-09999"),
                   ("RECORD_UNAUDITED", "SMP-00001")}


def test_correction_does_not_count_as_mismatch(con):
    """Corrections live in the audit_log only; the base row stays as inserted and still reconciles."""
    _load_both(con)
    audit.correct_record(con, "lims.custody_events", {"event_id": "EVT-000001"}, "location", "FRZ-01", "USR-02",
                         "relabel")
    assert audit.reconcile(con) == []
    assert audit.verify_chain(con).ok


def test_reconcile_records_writes_run_marker_and_issues(con):
    from pipeline.integrity import reconcile_records

    _load_both(con)
    assert reconcile_records(con) == 0
    con.execute("UPDATE lims.samples SET visit = 'D29' WHERE sample_id = 'SMP-00001'")
    assert reconcile_records(con) == 1
    rows = con.execute("SELECT issue, record_key, key_type FROM audit.record_reconciliation "
                       "ORDER BY checked_at, issue").fetchall()
    assert rows == [("RUN", None, None), ("RECORD_MODIFIED", "SMP-00001", "sample_id"), ("RUN", None, None)]


def test_tamper_base_row_reassigns_performer_and_is_caught(con):
    from generator.tamper import tamper_base_row

    _load_both(con)
    seq = tamper_base_row(con, "EVT-000002")
    who = con.execute("SELECT performed_by FROM lims.custody_events WHERE event_id = 'EVT-000002'").fetchone()[0]
    assert who == "USR-02"
    assert audit.verify_chain(con, records=False).ok  # the chain alone cannot see it ...
    res = audit.verify_chain(con)                      # ... the reconciliation does
    assert (res.check, res.first_broken_seq, res.broken_record_key) == ("RECORD", seq, "EVT-000002")
    with pytest.raises(KeyError):
        tamper_base_row(con, "EVT-999999")


# ---------------------------------------------------------------------------------------------------------------------
# BUG-004 (REVIEW F5): tail truncation / tail re-hash, via checkpoints and an external anchor
# ---------------------------------------------------------------------------------------------------------------------

def _row(con, seq):
    cols = ", ".join(audit.AUDIT_COLUMNS)
    values = con.execute(f"SELECT {cols} FROM audit.audit_log WHERE audit_seq = ?", [seq]).fetchone()
    return dict(zip(audit.AUDIT_COLUMNS, values, strict=True))


def _rehash_from(con, seq):
    """Simulate a capable forger: recompute prev_hash/row_hash for every row from `seq` to the end."""
    last = con.execute("SELECT max(audit_seq) FROM audit.audit_log").fetchone()[0]
    prev = _row(con, seq - 1)["row_hash"] if seq > 1 else audit.GENESIS_HASH
    for s in range(seq, last + 1):
        r = _row(con, s)
        h = audit.compute_row_hash(prev, r)
        con.execute("UPDATE audit.audit_log SET prev_hash = ?, row_hash = ? WHERE audit_seq = ?", [prev, h, s])
        prev = h


def test_every_write_appends_a_checkpoint(con):
    _load_both(con)
    cps = con.execute("SELECT checkpoint_seq, head_seq FROM audit.chain_checkpoint ORDER BY 1").fetchall()
    assert cps == [(1, 2), (2, 5), (3, 9)]


def test_tail_truncation_caught_by_checkpoint(con):
    _load_both(con)
    con.execute("DELETE FROM audit.audit_log WHERE audit_seq >= 8")
    res = audit.verify_chain(con, records=False)
    assert (res.ok, res.check, res.first_broken_seq, res.broken_record_key) == (False, "CHECKPOINT", 9, "EVT-000004")


def test_rows_appended_outside_api_caught(con):
    _load_both(con)
    last = _row(con, 9)
    new = {**last, "audit_seq": 10, "record_key": "EVT-000099", "prev_hash": last["row_hash"]}
    new["row_hash"] = audit.compute_row_hash(new["prev_hash"], new)
    marks = ", ".join(["?"] * len(audit.AUDIT_COLUMNS))
    con.execute(f"INSERT INTO audit.audit_log VALUES ({marks})", [new[c] for c in audit.AUDIT_COLUMNS])
    res = audit.verify_chain(con, records=False)
    assert (res.check, res.first_broken_seq) == ("CHECKPOINT", 10)


def test_forger_who_rewrites_checkpoints_is_caught_only_by_external_anchor(con, tmp_path):
    from pipeline.integrity import write_chain_anchor

    _load_both(con)
    anchor_path = tmp_path / "anchor.json"
    anchor = write_chain_anchor(con, anchor_path)
    assert anchor["head_seq"] == 9
    # forge: edit row 7, re-hash the tail, and rewrite the newest checkpoint to match
    con.execute("UPDATE audit.audit_log SET reason = 'forged' WHERE audit_seq = 7")
    _rehash_from(con, 7)
    new_head = _row(con, 9)["row_hash"]
    con.execute("UPDATE audit.chain_checkpoint SET head_hash = ? WHERE head_seq = 9", [new_head])
    assert audit.verify_chain(con, records=False).ok  # documented residual risk without the anchor
    res = audit.verify_chain(con, anchor=anchor_path, records=False)
    assert (res.ok, res.check, res.first_broken_seq) == (False, "ANCHOR", 9)


def test_anchor_file_is_write_once_and_read_only(con, tmp_path):
    import os
    import stat

    from pipeline.integrity import write_chain_anchor

    _load_both(con)
    p = tmp_path / "anchor.json"
    write_chain_anchor(con, p)
    with pytest.raises(FileExistsError):
        write_chain_anchor(con, p)
    with pytest.raises(PermissionError):
        p.write_text("{}")
    assert audit.verify_chain(con, anchor=json.loads(p.read_text())).ok
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
