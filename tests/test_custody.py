"""GXP-04 tests: chain of custody status and flags (AC-2.2 to AC-2.5, INJ-3).

Fixture tests run the dbt SQL on hand-made staging tables (see tests/integrity_sql.py). Build tests run on the
`built` / `clean_built` fixtures once DE-09 provides them, and skip until then.
"""

import pytest

from tests.integrity_sql import EVENTS, load_fixture, render_and_run


def _flags(rows):
    return {(r["flag_code"], r["key_type"], r["key"]): r["detail"] for r in rows}


def test_custody_flags_on_fixture():
    flags = _flags(render_and_run(load_fixture(), "custody_flags"))
    assert set(flags) == {
        ("CUSTODY_GAP", "sample_id", "SMP-00002"),
        ("CUSTODY_ORDER", "sample_id", "SMP-00003"),
        ("FREEZE_THAW_EXCEEDED", "aliquot_id", "ALQ-00003-1"),
    }
    assert flags[("CUSTODY_GAP", "sample_id", "SMP-00002")] == "missing step: received"  # AC-2.3 names the step
    assert "received" in flags[("CUSTODY_ORDER", "sample_id", "SMP-00003")]


def test_repeat_assay_after_stored_is_not_out_of_order():
    """DESIGN R8 / ADR 006: only the first occurrence of each step is compared."""
    flags = _flags(render_and_run(load_fixture(), "custody_flags"))
    assert not any(k == "SMP-00001" for _, _, k in flags)


def test_freeze_thaw_boundary():
    """At the limit (2) is fine; above it (3) is flagged (AC-2.5)."""
    flags = _flags(render_and_run(load_fixture(), "custody_flags"))
    ft = {k for c, _, k in flags if c == "FREEZE_THAW_EXCEEDED"}
    assert ft == {"ALQ-00003-1"}


def test_in_progress_sample_has_no_gap_flag():
    flags = _flags(render_and_run(load_fixture(), "custody_flags"))
    assert not any(k in ("SMP-00004", "SMP-00005") for _, _, k in flags)


def test_multiple_missing_steps_listed_in_order():
    events = [e for e in EVENTS if not (e[1] == "SMP-00001" and e[3] in ("received", "aliquoted"))]
    flags = _flags(render_and_run(load_fixture(events), "custody_flags"))
    assert flags[("CUSTODY_GAP", "sample_id", "SMP-00001")] == "missing step: received,aliquoted"


def test_custody_status_on_fixture():
    rows = {r["sample_id"]: r for r in render_and_run(load_fixture(), "v_custody_status")}
    assert len(rows) == 5  # every sample appears, even with no events
    assert rows["SMP-00001"]["custody_complete"] is True and rows["SMP-00001"]["missing_steps"] == ""
    assert rows["SMP-00001"]["current_step"] == "assayed"  # repeat assay is the latest event
    assert rows["SMP-00002"]["custody_complete"] is False and rows["SMP-00002"]["missing_steps"] == "received"
    assert rows["SMP-00004"]["current_step"] == "received"
    assert rows["SMP-00004"]["missing_steps"] == "aliquoted,assayed,stored"
    assert rows["SMP-00005"]["current_step"] is None
    assert rows["SMP-00005"]["missing_steps"] == "collected,received,aliquoted,assayed,stored"


# ---------------------------------------------------------------------------------------------------------------------
# Full-build checks (DE-09 `built` / `clean_built` fixtures)
# ---------------------------------------------------------------------------------------------------------------------

def _built(request, name):
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        pytest.skip(f"`{name}` fixture not available yet (DE-09)")


def test_inj3_flagged_with_received_missing(request):
    b = _built(request, "built")
    con, truth = b["con"], b["truth"]
    expected = set(truth.loc[truth["inj_type"] == "INJ-3", "affected_key"])
    assert expected, "INJ-3 missing from the manifest"
    got = dict(con.execute(
        "SELECT key, detail FROM integrity.custody_flags WHERE flag_code = 'CUSTODY_GAP'").fetchall())
    for key in expected:
        assert key in got, f"INJ-3 sample {key} not flagged CUSTODY_GAP"
        assert "received" in got[key]


def test_clean_data_has_no_custody_flags(request):
    con = _built(request, "clean_built")["con"]
    rows = con.execute("SELECT flag_code, key, detail FROM integrity.custody_flags").fetchall()
    assert rows == [], f"clean data produced custody flags: {rows[:10]}"
    incomplete = con.execute("SELECT count(*) FROM integrity.v_custody_status WHERE NOT custody_complete").fetchone()
    assert incomplete[0] == 0


def test_custody_flags_one_row_per_flag_and_key(request):
    con = _built(request, "built")["con"]
    dupes = con.execute("SELECT flag_code, key, count(*) FROM integrity.custody_flags GROUP BY 1, 2 "
                        "HAVING count(*) > 1").fetchall()
    assert dupes == []
