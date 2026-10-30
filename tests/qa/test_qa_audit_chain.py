"""QA edge tests: tampering with the audit trail from outside the API (AC-3.2, AC-3.3). In-memory DuckDB, no build.

Compares a direct edit of a middle row, the first row and the last row, plus deletions and edits that bypass
audit_log entirely. xfail(strict) = a logged bug in docs/team/BUGS.md.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from pipeline import audit

N = 6


@pytest.fixture()
def con():
    c = duckdb.connect()
    audit.init_audit(c)
    c.execute("create schema lims; create table lims.t (k varchar primary key, v integer)")
    audit.insert_records(c, "lims.t", pd.DataFrame({"k": list("abcdef"), "v": range(N)}), ["k"], "USR-01", "qa load")
    assert audit.verify_chain(c).ok
    yield c
    c.close()


@pytest.mark.parametrize("seq", [1, 3, N])
def test_direct_edit_detected_at_that_row(con, seq):
    """First row, a middle row, and the last row: verify names exactly the edited row."""
    con.execute("update audit.audit_log set reason = 'edited' where audit_seq = ?", [seq])
    r = audit.verify_chain(con)
    assert not r.ok and r.first_broken_seq == seq and r.broken_table_name == "lims.t"


def test_edit_of_hash_column_only_detected(con):
    con.execute("update audit.audit_log set row_hash = repeat('f', 64) where audit_seq = 2")
    r = audit.verify_chain(con)
    assert not r.ok and r.first_broken_seq == 2


def test_middle_row_deleted_detected(con):
    con.execute("delete from audit.audit_log where audit_seq = 3")
    r = audit.verify_chain(con)
    assert not r.ok and r.first_broken_seq == 4   # the row after the gap


def test_rows_swapped_detected(con):
    con.execute("update audit.audit_log set audit_seq = 100 where audit_seq = 2")
    con.execute("update audit.audit_log set audit_seq = 2 where audit_seq = 3")
    con.execute("update audit.audit_log set audit_seq = 3 where audit_seq = 100")
    assert not audit.verify_chain(con).ok


def test_middle_edit_with_rehash_of_that_row_still_detected(con):
    """A smarter tamperer recomputes the edited row's hash. The next row's prev_hash still breaks."""
    row = con.execute(f"select {', '.join(audit.AUDIT_COLUMNS)} from audit.audit_log where audit_seq = 3").fetchone()
    rec = dict(zip(audit.AUDIT_COLUMNS, row, strict=True))
    rec["new_value"] = '{"k":"c","v":999}'
    h = audit.compute_row_hash(rec["prev_hash"], rec)
    con.execute("update audit.audit_log set new_value = ?, row_hash = ? where audit_seq = 3", [rec["new_value"], h])
    r = audit.verify_chain(con)
    assert not r.ok and r.first_broken_seq == 4


def test_last_row_deleted_detected(con):
    con.execute(f"delete from audit.audit_log where audit_seq = {N}")
    assert not audit.verify_chain(con).ok


def test_last_row_edit_with_rehash_detected(con):
    row = con.execute(f"select {', '.join(audit.AUDIT_COLUMNS)} from audit.audit_log where audit_seq = {N}").fetchone()
    rec = dict(zip(audit.AUDIT_COLUMNS, row, strict=True))
    rec["new_value"] = '{"k":"f","v":999}'
    h = audit.compute_row_hash(rec["prev_hash"], rec)
    con.execute(f"update audit.audit_log set new_value = ?, row_hash = ? where audit_seq = {N}", [rec["new_value"], h])
    assert not audit.verify_chain(con).ok


def test_base_table_edit_detected(con):
    con.execute("update lims.t set v = 999 where k = 'c'")
    assert not audit.verify_chain(con).ok


def test_api_has_no_update_or_delete(con):
    with pytest.raises(audit.AppendOnlyError):
        audit.update(con, "lims.t", {"k": "a"}, "v", 1)
    with pytest.raises(audit.AppendOnlyError):
        audit.delete(con, "lims.t", {"k": "a"})


def test_reinsert_existing_key_refused_and_atomic(con):
    """Re-running a load into an existing DB must not overwrite or half-write anything."""
    before = con.execute("select count(*) from audit.audit_log").fetchone()[0]
    with pytest.raises(audit.AppendOnlyError):
        audit.insert_records(con, "lims.t", pd.DataFrame({"k": ["z", "a"], "v": [1, 2]}), ["k"], "USR-01", "rerun")
    assert con.execute("select count(*) from audit.audit_log").fetchone()[0] == before
    assert con.execute("select count(*) from lims.t where k = 'z'").fetchone()[0] == 0
    assert audit.verify_chain(con).ok


def test_blank_who_or_why_refused(con):
    for who, why in [("", "r"), ("USR-01", " "), (None, "r")]:
        with pytest.raises(ValueError):
            audit.insert_records(con, "lims.t", pd.DataFrame({"k": ["q"], "v": [1]}), ["k"], who, why)
