"""LIA-07: recompute KPIs and immunogenicity from base tables in pandas and match the marts (AC-9.3, AC-8.2, AC-8.5).

Independent of the dbt SQL and of pipeline.stats: reads only lims.* / assay.* (plus integrity.alcoa_findings for the
ALCOA numerator, whose logic GXP tests in test_alcoa.py) and uses scipy directly.
"""

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as st

from pipeline.config import load_rules

RULES = load_rules()
LLOQ = float(RULES["assay"]["assay_lloq_au_ml"])
IMPUTE = float(RULES["assay"]["lloq_impute_factor"])
FOLD = float(RULES["immunogenicity"]["seroresponse_fold"])
CONF = float(RULES["immunogenicity"]["ci_level"])
BASE = RULES["immunogenicity"]["baseline_visit"]
STEPS = RULES["custody"]["steps"]
PLATE_REASONS = ("FIT_FAIL", "STD_RECOVERY", "CTRL_OOR", "BLANK_HIGH", "INGEST_ERROR")


def q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


@pytest.fixture(scope="module")
def kpis(built):
    df = q(built["con"], "select * from marts.mart_lab_kpis")
    return df.set_index("kpi_id")


@pytest.fixture(scope="module")
def reportable(built):
    """One row per sample with a reportable result, rebuilt from base tables (ADR 003 analysis value)."""
    con = built["con"]
    df = q(con, """
        select sel.sample_id, r.run_at, r.range_flag, r.conc_au_ml, s.subject_id, s.visit, sub.group_name
        from assay.reportable_selection sel
        join assay.sample_results r on r.result_id = sel.result_id
        join lims.samples s on s.sample_id = sel.sample_id
        join lims.subjects sub on sub.subject_id = s.subject_id
        where sel.decision = 'REPORTABLE'
    """)
    in_range = (df["range_flag"] == "IN_RANGE") & (df["conc_au_ml"] >= LLOQ)
    df["value"] = np.where(in_range, df["conc_au_ml"], IMPUTE * LLOQ)
    return df


def test_mart_has_every_kpi(kpis):
    expected = {"TAT_MEDIAN_DAYS", "TAT_P90_DAYS", "PLATE_FAIL_RATE", "REASSAY_RATE", "CUSTODY_COMPLETE_PCT",
                "ALCOA_FINDINGS_PER_100"} | {f"PLATE_REJECT_{r}" for r in
                                             PLATE_REASONS}
    assert expected == set(kpis.index)


def test_turnaround_time(built, kpis, reportable):
    ev = q(built["con"], "select sample_id, performed_at from lims.custody_events where step = 'received'")
    rcv = ev.groupby("sample_id")["performed_at"].min()
    df = reportable.set_index("sample_id").join(rcv.rename("received_at"), how="inner")
    tat = (df["run_at"] - df["received_at"]).dt.total_seconds() / 86400.0
    assert kpis.loc["TAT_MEDIAN_DAYS", "denominator"] == len(tat)
    assert kpis.loc["TAT_MEDIAN_DAYS", "value"] == pytest.approx(tat.quantile(0.5), rel=1e-9)
    assert kpis.loc["TAT_P90_DAYS", "value"] == pytest.approx(tat.quantile(0.9), rel=1e-9)


def test_plate_failure_rate_and_reasons(built, kpis):
    ps = q(built["con"], "select plate_id, status, coalesce(reject_reasons, '') as reasons from assay.plate_status")
    rej = ps[ps["status"] == "REJECTED"]
    row = kpis.loc["PLATE_FAIL_RATE"]
    assert (row["numerator"], row["denominator"]) == (len(rej), len(ps))
    assert row["value"] == pytest.approx(100.0 * len(rej) / len(ps))
    for rule in PLATE_REASONS:
        n = sum(rule in [x.strip() for x in r.split(",")] for r in rej["reasons"])
        assert kpis.loc[f"PLATE_REJECT_{rule}", "value"] == n, rule
    # BUG-012: every reason seen in the data has its own KPI row
    seen = {x.strip() for r in rej["reasons"] for x in r.split(",") if x.strip()}
    assert seen <= set(PLATE_REASONS), f"reject reasons without a KPI row: {sorted(seen - set(PLATE_REASONS))}"


def test_reassay_rate(built, kpis):
    con = built["con"]
    res = q(con, "select sample_id, plate_id from assay.sample_results")
    flagged = q(con, "select sample_id, plate_id from assay.qc_flags where rule_id in ('ABOVE_ULOQ', 'DUP_CV')")
    rejected = set(q(con, "select plate_id from assay.plate_status where status = 'REJECTED'")["plate_id"])
    on_rejected = res[res["plate_id"].isin(rejected)]
    req = pd.concat([flagged, on_rejected]).merge(res, on=["sample_id", "plate_id"])
    num, den = req["sample_id"].nunique(), res["sample_id"].nunique()
    row = kpis.loc["REASSAY_RATE"]
    assert (row["numerator"], row["denominator"]) == (num, den)
    assert row["value"] == pytest.approx(100.0 * num / den)


def test_custody_complete_pct(built, kpis):
    con = built["con"]
    samples = q(con, "select sample_id from lims.samples")["sample_id"]
    ev = q(con, "select sample_id, step from lims.custody_events")
    steps = ev.groupby("sample_id")["step"].agg(set)
    complete = sum(set(STEPS) <= steps.get(s, set()) for s in samples)
    row = kpis.loc["CUSTODY_COMPLETE_PCT"]
    assert (row["numerator"], row["denominator"]) == (complete, len(samples))
    assert row["value"] == pytest.approx(100.0 * complete / len(samples))


def test_alcoa_findings_per_100(built, kpis):
    con = built["con"]
    findings = con.execute("select count(*) from integrity.alcoa_findings").fetchone()[0]
    records = con.execute("select count(*) from lims.custody_events").fetchone()[0]
    row = kpis.loc["ALCOA_FINDINGS_PER_100"]
    assert (row["numerator"], row["denominator"]) == (findings, records)
    assert row["value"] == pytest.approx(100.0 * findings / records)


# --- Immunogenicity (US-8) -----------------------------------------------------------------------------------------

def _geo(vals):
    logs = np.log10(np.asarray(vals, dtype=float))
    m, n = logs.mean(), len(logs)
    h = st.t.ppf((1 + CONF) / 2, n - 1) * logs.std(ddof=1) / math.sqrt(n)
    return 10**m, 10 ** (m - h), 10 ** (m + h)


@pytest.fixture(scope="module")
def immuno(built):
    return q(built["con"], "select * from marts.mart_immunogenicity").set_index(["group_name", "visit"])


def test_gmt_matches_recompute(immuno, reportable):
    for (grp, visit), g in reportable.groupby(["group_name", "visit"]):
        gmt, lcl, ucl = _geo(g["value"])
        row = immuno.loc[(grp, visit)]
        assert row["n"] == len(g)
        assert (row["gmt"], row["gmt_lcl"], row["gmt_ucl"]) == pytest.approx((gmt, lcl, ucl), rel=1e-9)


def test_gmfr_and_seroresponse_use_paired_subjects_only(immuno, reportable):
    """AC-8.2: GMFR and seroresponse N count only subjects with both a baseline and a post value."""
    base = reportable[reportable["visit"] == BASE][["subject_id", "value"]].rename(columns={"value": "b"})
    post_rows = reportable[reportable["visit"] != BASE]
    checked = 0
    for (grp, visit), g in post_rows.groupby(["group_name", "visit"]):
        paired = g.merge(base, on="subject_id")
        row = immuno.loc[(grp, visit)]
        assert row["gmfr_n"] == row["sero_total"] == len(paired)
        assert row["gmfr"] == pytest.approx(_geo(paired["value"] / paired["b"])[0], rel=1e-9)
        resp = np.where(paired["b"] < LLOQ, paired["value"] >= FOLD * LLOQ, paired["value"] >= FOLD * paired["b"])
        assert row["sero_n"] == int(resp.sum())
        checked += 1
    assert checked > 0
    # the baseline rows carry no GMFR / seroresponse
    for grp in reportable["group_name"].unique():
        assert pd.isna(immuno.loc[(grp, BASE), "gmfr"]) and pd.isna(immuno.loc[(grp, BASE), "sero_pct"])


def test_vaccine_d29_seroresponse_beats_placebo(immuno):
    """AC-8.5 on the full seeded run."""
    assert immuno.loc[("Vaccine", "D29"), "sero_pct"] > immuno.loc[("Placebo", "D29"), "sero_pct"]


# --- REVIEW F11: unit test of the dbt Python model's row builder (no DB) --------------------------------------------

def _load_model_module():
    import importlib.util

    from pipeline.config import ROOT

    path = ROOT / "dbt" / "models" / "marts" / "mart_immunogenicity.py"
    spec = importlib.util.spec_from_file_location("mart_immunogenicity_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_rows_pairs_subjects_and_nulls_baseline():
    from pipeline import stats

    mod = _load_model_module()
    imp = IMPUTE * LLOQ
    fct = pd.DataFrame({
        "subject_id": ["S1", "S2", "S3", "S1", "S2", "S3", "S4"],
        "group_name": ["Vaccine"] * 7,
        "visit": ["D1", "D1", "D1", "D29", "D29", "D29", "D29"],
        "visit_day": [1, 1, 1, 29, 29, 29, 29],
        # S1: <LLOQ -> 4xLLOQ (responder); S2: 100 -> 400 (exactly 4x, responder); S3: 100 -> 300 (no);
        # S4: no D1 -> excluded from GMFR and seroresponse but counted in the D29 GMT n
        "analysis_value_au_ml": [imp, 100.0, 100.0, 4 * LLOQ, 400.0, 300.0, 5000.0],
    })
    rows = {r["visit"]: r for r in mod.build_rows(fct, stats, CONF, FOLD, LLOQ, BASE)}
    d1, d29 = rows["D1"], rows["D29"]
    assert d1["n"] == 3 and all(d1[k] is None for k in ("gmfr", "gmfr_n", "sero_n", "sero_total", "sero_pct"))
    assert d29["n"] == 4
    assert d29["gmfr_n"] == d29["sero_total"] == 3
    assert d29["sero_n"] == 2
    assert d29["sero_pct"] == pytest.approx(200 / 3)
    ratios = np.array([4 * LLOQ / imp, 4.0, 3.0])
    assert d29["gmfr"] == pytest.approx(10 ** np.log10(ratios).mean())
