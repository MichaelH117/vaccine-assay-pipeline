"""QC rules at their threshold boundaries, plate status, and planted plates on the full build (US-6)."""

from __future__ import annotations

import pandas as pd

from pipeline.config import load_rules
from pipeline.qc import plate_flags, sample_flags

RULES = load_rules()
EMPTY_REC = pd.DataFrame(columns=["plate_id", "within_limits"])
EMPTY_CTRL = pd.DataFrame(columns=["plate_id", "ctrl_level", "mean_conc", "target_conc", "low_limit", "high_limit"])
EMPTY_BLANK = pd.DataFrame(columns=["plate_id", "mean_blank_od"])
EMPTY_FIT = pd.DataFrame(columns=["plate_id", "converged", "r_squared", "fit_message"])


def _rules(flags):
    return sorted(f["rule_id"] for f in flags)


def _fit(r2, converged=True):
    return pd.DataFrame([dict(plate_id="P", converged=converged, r_squared=r2, fit_message="m")])


def _rec(n_pass, n=8):
    return pd.DataFrame(dict(plate_id="P", within_limits=[True] * n_pass + [False] * (n - n_pass)))


def test_fit_fail_boundary():
    thr = RULES["fit"]["min_r_squared"]
    assert _rules(plate_flags(_fit(thr), _rec(8), EMPTY_CTRL, EMPTY_BLANK, RULES)) == []
    f = plate_flags(_fit(thr - 1e-6), _rec(8), EMPTY_CTRL, EMPTY_BLANK, RULES)
    assert _rules(f) == ["FIT_FAIL"] and f[0]["threshold"] == f">={thr}" and f[0]["measured_value"] < thr
    assert _rules(plate_flags(_fit(None, converged=False), _rec(8), EMPTY_CTRL, EMPTY_BLANK, RULES)) == ["FIT_FAIL"]


def test_std_recovery_boundary():  # 6 of 8 = 0.75 passes, 5 of 8 fails
    assert _rules(plate_flags(_fit(0.999), _rec(6), EMPTY_CTRL, EMPTY_BLANK, RULES)) == []
    assert _rules(plate_flags(_fit(0.999), _rec(5), EMPTY_CTRL, EMPTY_BLANK, RULES)) == ["STD_RECOVERY"]


def test_ctrl_oor_boundary():
    def ctrl(conc):
        return pd.DataFrame([dict(plate_id="P", ctrl_level="HIGH", mean_conc=conc, target_conc=300.0,
                                  low_limit=240.0, high_limit=360.0)])
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, ctrl(360.0), EMPTY_BLANK, RULES)) == []
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, ctrl(240.0), EMPTY_BLANK, RULES)) == []
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, ctrl(360.01), EMPTY_BLANK, RULES)) == ["CTRL_OOR"]
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, ctrl(None), EMPTY_BLANK, RULES)) == ["CTRL_OOR"]


def test_ctrl_oor_not_cascaded_from_a_failed_fit():  # review F3
    ctrl = pd.DataFrame([dict(plate_id="P", ctrl_level="HIGH", mean_conc=None, target_conc=300.0,
                              low_limit=240.0, high_limit=360.0)])
    assert _rules(plate_flags(_fit(0.5), _rec(8), ctrl, EMPTY_BLANK, RULES)) == ["FIT_FAIL"]
    assert _rules(plate_flags(_fit(0.999), _rec(8), ctrl, EMPTY_BLANK, RULES)) == ["CTRL_OOR"]


def test_blank_high_boundary():
    thr = RULES["plate"]["max_mean_blank_od"]
    b = lambda v: pd.DataFrame([dict(plate_id="P", mean_blank_od=v)])  # noqa: E731
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, EMPTY_CTRL, b(thr), RULES)) == []
    assert _rules(plate_flags(EMPTY_FIT, EMPTY_REC, EMPTY_CTRL, b(thr + 0.001), RULES)) == ["BLANK_HIGH"]


def _sr(**kw):
    base = dict(plate_id="P", sample_id="S", od_cv_pct=5.0, range_flag="IN_RANGE", conc_au_ml=500.0, mean_od=1.0,
                dilution=100)
    return pd.DataFrame([{**base, **kw}])


def test_dup_cv_boundary_and_blocking():
    thr = RULES["sample"]["max_dup_cv_pct"]
    assert sample_flags(_sr(od_cv_pct=thr), {"P"}, RULES) == []
    f = sample_flags(_sr(od_cv_pct=thr + 0.01), set(), RULES)   # DUP_CV is raised on rejected plates too
    assert _rules(f) == ["DUP_CV"] and f[0]["blocking"]


def test_range_flags_on_accepted_plates_only():
    lloq = RULES["assay"]["assay_lloq_au_ml"]
    assert _rules(sample_flags(_sr(range_flag="<LLOQ", conc_au_ml=None), {"P"}, RULES)) == ["BELOW_LLOQ"]
    assert _rules(sample_flags(_sr(conc_au_ml=lloq), {"P"}, RULES)) == []
    below = sample_flags(_sr(conc_au_ml=lloq - 0.01), {"P"}, RULES)
    assert _rules(below) == ["BELOW_LLOQ"] and not below[0]["blocking"]
    above = sample_flags(_sr(range_flag=">ULOQ", conc_au_ml=None), {"P"}, RULES)
    assert _rules(above) == ["ABOVE_ULOQ"] and above[0]["blocking"]
    assert sample_flags(_sr(range_flag=">ULOQ", conc_au_ml=None), set(), RULES) == []


# ---- full build ----

def test_exactly_the_inj1_and_inj5_plates_rejected(built):  # review F2: no false plate rejects either
    con, truth = built["con"], built["truth"]
    planted = set(truth.loc[truth.inj_type.isin(["INJ-1", "INJ-5"]), "affected_key"])
    status = dict(con.execute("select plate_id, status from assay.plate_status").fetchall())
    assert {p for p, s in status.items() if s == "REJECTED"} == planted
    inj5 = truth.loc[truth.inj_type == "INJ-5", "affected_key"].item()
    reasons = dict(con.execute("select plate_id, reject_reasons from assay.plate_status").fetchall())
    assert reasons[inj5] == "CTRL_OOR"   # INJ-5 is caught by the control rule itself, with a good curve


def test_any_plate_flag_means_rejected(built):
    con = built["con"]
    bad = con.execute("""
        select p.plate_id from assay.plate_status p
        left join (select distinct plate_id from assay.qc_flags where level = 'PLATE') f using (plate_id)
        where (f.plate_id is not null) <> (p.status = 'REJECTED')""").fetchall()
    assert bad == []


def test_every_flag_has_version_value_or_threshold(built):  # AC-6.5
    con = built["con"]
    v = load_rules()["version"]
    rows = con.execute("select rule_version, threshold from assay.qc_flags").fetchall()
    assert rows and all(r[0] == v and r[1] for r in rows)


def test_clean_build_rejects_no_plate(clean_built):
    assert clean_built["con"].execute(
        "select count(*) from assay.plate_status where status = 'REJECTED'").fetchone()[0] == 0
