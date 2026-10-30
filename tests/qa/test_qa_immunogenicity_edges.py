"""QA edge tests for mart_immunogenicity.build_rows (AC-8.1 to 8.3, ADR 003): missing visits, all <LLOQ, n=1.
Pure: the dbt Python model's row builder is imported straight from its file."""

from __future__ import annotations

import importlib.util
import math

import pandas as pd
import pytest

from pipeline import stats
from pipeline.config import ROOT, load_rules

_spec = importlib.util.spec_from_file_location("mart_immuno", ROOT / "dbt" / "models" / "marts" /
                                               "mart_immunogenicity.py")
mart = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mart)

R = load_rules()
LLOQ = float(R["assay"]["assay_lloq_au_ml"])
IMPUTED = LLOQ * float(R["assay"]["lloq_impute_factor"])
DAY = {"D1": 1, "D29": 29, "D57": 57}


def fct(rows):
    return pd.DataFrame([dict(subject_id=s, group_name=g, visit=v, visit_day=DAY[v], analysis_value_au_ml=x)
                         for s, g, v, x in rows])


def rows_by(rows):
    return {(r["group_name"], r["visit"]): r for r in mart.build_rows(rows, stats, 0.95, 4.0, LLOQ, "D1")}


def test_baseline_only_subject_excluded_from_gmfr_but_in_gmt():
    out = rows_by(fct([("S1", "Vaccine", "D1", 50.0), ("S1", "Vaccine", "D29", 800.0),
                       ("S2", "Vaccine", "D1", 60.0), ("S2", "Vaccine", "D29", 900.0),
                       ("S3", "Vaccine", "D1", 70.0)]))          # S3: baseline, no post
    assert out[("Vaccine", "D1")]["n"] == 3
    d29 = out[("Vaccine", "D29")]
    assert d29["n"] == 2 and d29["gmfr_n"] == 2 and d29["sero_total"] == 2
    assert d29["gmfr"] == pytest.approx(math.sqrt(800 / 50 * 900 / 60), rel=1e-9)


def test_post_only_subject_excluded_from_gmfr():
    out = rows_by(fct([("S1", "Placebo", "D1", 50.0), ("S1", "Placebo", "D29", 55.0),
                       ("S2", "Placebo", "D29", 5000.0)]))       # S2: no baseline
    d29 = out[("Placebo", "D29")]
    assert d29["n"] == 2 and d29["gmfr_n"] == 1 and d29["gmfr"] == pytest.approx(1.1)


def test_group_with_no_paired_subjects_gives_nulls_not_crash():
    out = rows_by(fct([("S1", "Vaccine", "D1", 50.0), ("S2", "Vaccine", "D29", 500.0)]))
    d29 = out[("Vaccine", "D29")]
    assert d29["gmfr_n"] == 0 and d29["gmfr"] is None and d29["sero_pct"] is None


def test_all_subjects_below_lloq():
    rows = [(f"S{i}", "Placebo", v, IMPUTED) for i in range(5) for v in ("D1", "D29")]
    out = rows_by(fct(rows))
    d1, d29 = out[("Placebo", "D1")], out[("Placebo", "D29")]
    assert d1["gmt"] == pytest.approx(IMPUTED)
    assert d1["gmt_lcl"] == pytest.approx(IMPUTED) and d1["gmt_ucl"] == pytest.approx(IMPUTED)  # zero spread
    assert d29["gmfr"] == pytest.approx(1.0) and d29["sero_n"] == 0 and d29["sero_pct"] == 0.0
    assert d29["sero_lcl"] == 0.0 and 0 < d29["sero_ucl"] < 100


def test_below_lloq_baseline_needs_4x_lloq_not_4x_imputed():
    """Baseline imputed to 0.5 x LLOQ: a post of 4 x imputed (= 2 x LLOQ) is NOT a seroresponse (ADR 003)."""
    out = rows_by(fct([("S1", "Vaccine", "D1", IMPUTED), ("S1", "Vaccine", "D29", 4 * IMPUTED),
                       ("S2", "Vaccine", "D1", IMPUTED), ("S2", "Vaccine", "D29", 4 * LLOQ)]))
    assert out[("Vaccine", "D29")]["sero_n"] == 1


def test_single_subject_group_has_point_but_no_ci():
    d1 = rows_by(fct([("S1", "Vaccine", "D1", 100.0)]))[("Vaccine", "D1")]
    assert d1["gmt"] == pytest.approx(100.0) and d1["gmt_lcl"] is None and d1["gmt_ucl"] is None


def test_zero_value_rejected_loudly():
    """A 0 or negative analysis value must fail, not be logged as -inf (imputation must happen first)."""
    with pytest.raises(ValueError):
        mart.build_rows(fct([("S1", "Vaccine", "D1", 0.0), ("S2", "Vaccine", "D1", 10.0)]), stats, 0.95, 4.0,
                        LLOQ, "D1")
