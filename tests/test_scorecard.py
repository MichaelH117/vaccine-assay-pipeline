"""Detection scorecard on the full seeded build (US-10, AC-10.1 to 10.3; REVIEW F2, F3, F6). Uses `built`."""

import shutil

import duckdb
import pytest

from pipeline.config import load_rules

RULES = load_rules()
# BUG-010: the required set comes from config (INJ-1..8 plus INJ-11), never from the planted manifest, so a dropped
# injection makes these tests fail instead of shrinking both sides of the comparison.
REQUIRED = list(RULES["scorecard"]["required_inj_types"])

# Hand-written answer key for how each required INJ type must be caught on seed 42 (REVIEW F6: independent of the
# scorecard SQL, so a wrong join or a changed QC rule makes this fail).
EXPECTED_CAUGHT_BY = {
    "INJ-1": "FIT_FAIL,STD_RECOVERY",
    "INJ-2": "ID_MISMATCH",
    "INJ-3": "CUSTODY_GAP",
    "INJ-4": "LATE_ENTRY",
    "INJ-5": "CTRL_OOR",
    "INJ-6": "DUP_CV",
    "INJ-7": "AUDIT_CHAIN_BROKEN",
    "INJ-8": "ABOVE_ULOQ",
    "INJ-11": "RECORD_MISMATCH",
}


def test_scorecard_has_one_row_per_injected_key(built):
    con = built["con"]
    n_truth = con.execute("select count(*) from truth.injected_problems").fetchone()[0]
    n_card = con.execute("select count(*) from marts.detection_scorecard").fetchone()[0]
    assert n_truth > 0
    assert n_card == n_truth


def test_every_required_inj_type_is_planted(built):
    types = set(built["con"].execute("select distinct inj_type from marts.detection_scorecard").df()["inj_type"])
    assert set(REQUIRED) <= types, f"missing INJ types in the manifest: {sorted(set(REQUIRED) - types)}"


def test_recall_is_100pct_for_required_types(built):
    df = built["con"].execute(
        "select problem_id, inj_type, key_type, affected_key, detected, masked_by from marts.detection_scorecard "
        "where inj_type in (" + ",".join(f"'{t}'" for t in REQUIRED) + ") order by problem_id, affected_key"
    ).df()
    misses = df[~df["detected"].astype(bool)]
    assert misses.empty, "planted problems NOT detected:\n" + misses.to_string(index=False)


def test_answer_key_covers_every_required_type():
    assert set(EXPECTED_CAUGHT_BY) == set(REQUIRED), "update EXPECTED_CAUGHT_BY when required_inj_types changes"


def test_inj11_record_edit_is_planted_and_caught(built):
    """BUG-010: fast, targeted INJ-11 check (a direct base-row edit caught only by RECORD_MISMATCH)."""
    df = built["con"].execute("select key_type, affected_key, detected, caught_by from marts.detection_scorecard "
                              "where inj_type = 'INJ-11'").df()
    assert len(df) >= 1, "INJ-11 is missing from the planted manifest"
    assert df["detected"].astype(bool).all(), "INJ-11 planted but NOT detected: " + df.to_string(index=False)
    assert (df["caught_by"] == "RECORD_MISMATCH").all()


def test_caught_by_matches_hand_written_answer_key(built):
    """F6 replacement: exact flag codes per INJ type, each confirmed present in the raw flag sources."""
    con = built["con"]
    df = con.execute("select inj_type, key_type, affected_key, caught_by from marts.detection_scorecard "
                     "where inj_type in (" + ",".join(f"'{t}'" for t in REQUIRED) + ")").df()
    raw = con.execute("""
        select rule_id as code, case when level = 'PLATE' then plate_id else sample_id end as key from assay.qc_flags
        union all select flag_code, key from integrity.custody_flags
        union all select flag_code, key from integrity.alcoa_findings
        union all select 'AUDIT_CHAIN_BROKEN', broken_record_key from audit.chain_verify where not ok
    """).df()
    raw_pairs = set(zip(raw["code"], raw["key"], strict=True))
    for r in df.itertuples(index=False):
        assert r.caught_by == EXPECTED_CAUGHT_BY[r.inj_type], f"{r.inj_type} {r.affected_key}: {r.caught_by}"
        for code in r.caught_by.split(","):
            assert (code, r.affected_key) in raw_pairs, f"{code} on {r.affected_key} not in the raw flag tables"


def test_rejected_plates_are_exactly_the_injected_plates(built):
    """F2: no false rejects in the dirty build; every non-injected plate is ACCEPTED."""
    con = built["con"]
    rejected = set(con.execute("select plate_id from assay.plate_status where status = 'REJECTED'").df()["plate_id"])
    injected = set(con.execute("select affected_key from truth.injected_problems where key_type = 'plate_id' "
                               "and inj_type in ('INJ-1', 'INJ-5')").df()["affected_key"])
    assert injected, "no injected plates in the manifest"
    extra, missed = sorted(rejected - injected), sorted(injected - rejected)
    assert rejected == injected, f"unexpected rejects {extra}; missed {missed}"
    fp = con.execute("select plates_rejected_unexplained, plate_fp_pct, unexplained_plate_ids "
                     "from marts.scorecard_false_positives").fetchone()
    assert fp == (0, 0.0, "")


def test_false_positive_rate_reported_and_within_target(built):
    max_pct = float(RULES["scorecard"]["max_unexplained_flag_pct"])
    row = built["con"].execute("select * from marts.scorecard_false_positives").df()
    assert len(row) == 1
    total, unexplained, fp = row.iloc[0][["samples_total", "samples_with_unexplained_flag", "fp_pct"]]
    assert total > 0
    assert fp == pytest.approx(100.0 * unexplained / total)
    print(f"FP: {unexplained}/{total} samples = {fp:.2f}% (target <= {max_pct}%)")
    assert fp <= max_pct, f"unexplained sample-level flags {fp:.2f}% exceed {max_pct}%"


def test_summary_counts_problems_not_keys(built):
    """One headline number: problems (problem_id). INJ-2 is one problem with two keys."""
    con = built["con"]
    truth = built["truth"]
    s = con.execute("select * from marts.scorecard_summary").df().iloc[0]
    assert s["problems_planted"] == truth["problem_id"].nunique()
    assert s["keys_planted"] == len(truth)
    required = load_rules()["scorecard"]["required_inj_types"]   # config, not REQUIRED: INJ-11 is required too
    req = truth[truth["inj_type"].isin(required)]
    assert s["required_problems_planted"] == req["problem_id"].nunique()
    assert s["required_problems_detected"] == s["required_problems_planted"]
    assert s["required_inj_types_planted"] == s["required_inj_types_expected"] == len(REQUIRED)
    assert s["required_recall_pct"] == 100.0
    assert s["optional_problems_planted"] == truth.loc[~truth["inj_type"].isin(required), "problem_id"].nunique()
    assert s["missed_problem_ids"] == ""
    n = req["problem_id"].nunique()
    assert s["headline"].startswith(f"{n} of {n} required planted problems caught ({len(req)} of {len(req)} affected")
    print(s["headline"])


# --- F3: INJ-5 must be caught by the control rule itself, not by a cascade from a broken curve --------------------

@pytest.fixture(scope="module")
def scorecard_sandbox(built, tmp_path_factory):
    """A writable copy of the built DB plus the compiled detection_scorecard SELECT."""
    db = built["paths"].db
    compiled = next((db.parent / "dbt_target" / "compiled").rglob("detection_scorecard.sql"))
    copy_dir = tmp_path_factory.mktemp("sandbox")
    copy = copy_dir / db.name  # same file name -> same catalog name as in the compiled SQL
    shutil.copy(db, copy)
    plate = built["con"].execute("select affected_key from truth.injected_problems where inj_type = 'INJ-5'"
                                 ).fetchone()[0]
    return copy, compiled.read_text(), plate


def _inj5_detected(copy, sql: str, mutate: str | None, plate: str) -> bool:
    con = duckdb.connect(str(copy))
    try:
        con.execute("begin")
        if mutate:
            con.execute(mutate, [plate])
        df = con.execute(f"select detected from ({sql}) where inj_type = 'INJ-5'").df()
        con.execute("rollback")
    finally:
        con.close()
    assert len(df) == 1
    return bool(df["detected"].iloc[0])


def test_inj5_detected_on_unchanged_copy(scorecard_sandbox):
    copy, sql, plate = scorecard_sandbox
    assert _inj5_detected(copy, sql, None, plate)


def test_inj5_not_detected_without_ctrl_oor(scorecard_sandbox):
    copy, sql, plate = scorecard_sandbox
    assert not _inj5_detected(copy, sql, "delete from assay.qc_flags where plate_id = ? and rule_id = 'CTRL_OOR'",
                              plate)


def test_inj5_not_detected_when_curve_also_failed(scorecard_sandbox):
    """CTRL_OOR on a plate that also failed its fit is a cascade, so it does not prove the control rule."""
    copy, sql, plate = scorecard_sandbox
    mutate = ("insert into assay.qc_flags select * replace (flag_id || '-SANDBOX' as flag_id, 'FIT_FAIL' as rule_id) "
              "from assay.qc_flags where plate_id = ? and rule_id = 'CTRL_OOR' limit 1")
    assert not _inj5_detected(copy, sql, mutate, plate)
