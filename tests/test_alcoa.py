"""GXP-03 / GXP-05 tests: Original (raw file re-hash) and the dbt alcoa_findings model (AC-3.4, AC-3.5, INJ-4)."""

import os
import stat

import duckdb
import pytest

from pipeline import audit
from pipeline.integrity import rehash_raw_files, sha256_file
from tests.integrity_sql import load_fixture, render_and_run


@pytest.fixture
def raw_con(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    con = duckdb.connect(":memory:")
    audit.init_audit(con)
    con.execute("CREATE SCHEMA lims")
    con.execute("CREATE TABLE lims.raw_files (file_name VARCHAR, plate_id VARCHAR, raw_path VARCHAR, "
                "sha256 VARCHAR, ingested_at TIMESTAMP)")
    for i in (1, 2, 3):
        p = raw / f"PLATE-00{i}.csv"
        p.write_bytes(b",1,2\nA,0.101,0.202\n")
        con.execute("INSERT INTO lims.raw_files VALUES (?, ?, ?, ?, now())",
                    [p.name, f"PLATE-00{i}", str(p), sha256_file(p)])
        os.chmod(p, stat.S_IREAD)  # read-only, as ingest does (AC-3.5)
    yield con, raw
    for p in raw.iterdir():
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    con.close()


def test_rehash_clean_files_all_match(raw_con):
    con, raw = raw_con
    assert rehash_raw_files(con, raw) == 0
    assert con.execute("SELECT count(*), bool_and(matches) FROM audit.file_integrity").fetchone() == (3, True)


def test_raw_files_are_read_only(raw_con):
    """AC-3.5: the copies cannot be written without first changing their mode."""
    _, raw = raw_con
    with pytest.raises(PermissionError):
        (raw / "PLATE-001.csv").write_bytes(b"edited")


def test_edited_raw_file_gives_mismatch(raw_con):
    """AC-3.4 Original: make a copied raw file writable, edit it, and the re-hash catches it."""
    con, raw = raw_con
    p = raw / "PLATE-002.csv"
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    p.write_bytes(b",1,2\nA,0.101,0.999\n")
    os.chmod(raw / "PLATE-003.csv", stat.S_IWRITE | stat.S_IREAD)
    os.remove(raw / "PLATE-003.csv")
    assert rehash_raw_files(con, raw) == 2
    bad = con.execute("SELECT plate_id, current_sha256 IS NULL FROM audit.file_integrity WHERE NOT matches "
                      "ORDER BY plate_id").fetchall()
    assert bad == [("PLATE-002", False), ("PLATE-003", True)]


# ---------------------------------------------------------------------------------------------------------------------
# alcoa_findings.sql on hand-made staging fixtures (contract columns), rendered with a minimal ref/var shim
# ---------------------------------------------------------------------------------------------------------------------

def test_alcoa_findings_on_fixture():
    con = load_fixture()
    rows = render_and_run(con, "alcoa_findings", deps=["custody_flags"])
    got = {(r["rule_id"], r["attribute"], r["flag_code"], r["key_type"], r["key"]) for r in rows}
    assert got == {
        ("ALCOA-A1", "Attributable", "NO_PERFORMER", "event_id", "EVT-000011"),
        ("ALCOA-A2", "Attributable", "UNKNOWN_USER", "event_id", "EVT-000012"),
        ("ALCOA-C1", "Contemporaneous", "LATE_ENTRY", "event_id", "EVT-000007"),
        ("ALCOA-O1", "Original", "HASH_MISMATCH", "plate_id", "PLATE-002"),
        ("ALCOA-O2", "Original", "RECORD_MISMATCH", "event_id", "EVT-000004"),
        ("ALCOA-CM1", "Complete", "CUSTODY_GAP", "sample_id", "SMP-00002"),
    }
    assert len({r["finding_id"] for r in rows}) == len(rows)


def test_late_entry_boundary_is_strictly_greater_than_limit():
    con = load_fixture()
    # EVT-000006 is recorded exactly 24h after performed_at: not late. EVT-000007 is 24h + 1s: late.
    rows = render_and_run(con, "alcoa_findings", deps=["custody_flags"])
    late = {r["key"] for r in rows if r["flag_code"] == "LATE_ENTRY"}
    assert late == {"EVT-000007"}


# ---------------------------------------------------------------------------------------------------------------------
# Full-build checks (run once DE-09 provides the `built` fixture in tests/conftest.py)
# ---------------------------------------------------------------------------------------------------------------------

def _built(request, name="built"):
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        pytest.skip(f"`{name}` fixture not available yet (DE-09)")


def test_inj4_late_entry_detected_on_build(request):
    b = _built(request)
    con, truth = b["con"], b["truth"]
    expected = set(truth.loc[truth["inj_type"] == "INJ-4", "affected_key"])
    assert expected, "INJ-4 missing from the manifest"
    found = {r[0] for r in con.execute(
        "SELECT key FROM integrity.alcoa_findings WHERE flag_code = 'LATE_ENTRY'").fetchall()}
    assert expected <= found


def test_raw_files_match_on_build(request):
    con = _built(request)["con"]
    n, ok = con.execute("SELECT count(*), bool_and(matches) FROM audit.file_integrity").fetchone()
    assert n > 0 and ok
    assert con.execute("SELECT count(*) FROM integrity.alcoa_findings WHERE flag_code = 'HASH_MISMATCH'"
                       ).fetchone()[0] == 0
