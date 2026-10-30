"""Unit tests for pipeline.stats against hand-calculated values (AC-8.4, ADR 003). No database."""

import math

import numpy as np
import pytest

from pipeline.stats import clopper_pearson, gmfr_ci, gmt_ci, is_seroresponder


def sig3(x: float) -> float:
    """Round to 3 significant figures."""
    return float(f"{x:.3g}")


# --- GMT/GMC -------------------------------------------------------------------------------------------------------
# 5 subjects, values (AU/mL): 10, 100, 1000, 100, 100
#   log10:            1, 2, 3, 2, 2            mean = 10 / 5 = 2.0   -> GMT = 10^2 = 100
#   deviations:      -1, 0, 1, 0, 0           SS = 2, var = 2 / (5-1) = 0.5, SD = 0.70711
#   SE = 0.70711 / sqrt(5) = 0.31623
#   t(0.975, df=4) = 2.7764 (t table)         half-width = 2.7764 x 0.31623 = 0.87799
#   LCL = 10^(2 - 0.87799) = 10^1.12201 = 13.2
#   UCL = 10^(2 + 0.87799) = 10^2.87799 = 755
def test_gmt_hand_calculated_5_subjects():
    gmt, lcl, ucl = gmt_ci([10, 100, 1000, 100, 100])
    assert sig3(gmt) == 100.0
    assert sig3(lcl) == 13.2
    assert sig3(ucl) == 755.0


# --- GMFR ----------------------------------------------------------------------------------------------------------
# Same 5 subjects, baseline 50, 100, 200, 100, 100 and post 400, 800, 800, 1600, 400.
#   fold rises:       8, 8, 4, 16, 4    -> log2: 3, 3, 2, 4, 2   mean = 14 / 5 = 2.8   -> GMFR = 2^2.8 = 6.96
#   (a CI on log2 equals a CI on log10 after back-transformation, so log2 keeps the arithmetic exact)
#   deviations: 0.2, 0.2, -0.8, 1.2, -0.8    SS = 2.8, var = 0.7, SD = 0.83666, SE = 0.83666 / sqrt(5) = 0.37417
#   half-width = 2.7764 x 0.37417 = 1.03885 (log2 units)
#   LCL = 2^(2.8 - 1.03885) = 2^1.76115 = 3.39
#   UCL = 2^(2.8 + 1.03885) = 2^3.83885 = 14.3
def test_gmfr_hand_calculated_5_subjects():
    gmfr, lcl, ucl = gmfr_ci(post=[400, 800, 800, 1600, 400], base=[50, 100, 200, 100, 100])
    assert sig3(gmfr) == 6.96
    assert sig3(lcl) == 3.39
    assert sig3(ucl) == 14.3


def test_gmfr_is_paired_not_ratio_of_gmts():
    # GMFR of paired ratios equals GMT(post)/GMT(base) for complete pairs; check the pairing is enforced.
    with pytest.raises(ValueError):
        gmfr_ci([1, 2, 3], [1, 2])


def test_gmt_ci_level_widens_with_confidence():
    vals = [10, 100, 1000, 100, 100]
    _, l90, u90 = gmt_ci(vals, conf=0.90)
    _, l95, u95 = gmt_ci(vals, conf=0.95)
    assert l95 < l90 < 100 < u90 < u95


def test_gmt_single_value_has_no_ci_and_empty_is_nan():
    gmt, lcl, ucl = gmt_ci([250.0])
    assert gmt == pytest.approx(250.0)
    assert math.isnan(lcl) and math.isnan(ucl)
    assert all(math.isnan(x) for x in gmt_ci([]))


def test_gmt_identical_values_zero_width():
    gmt, lcl, ucl = gmt_ci([22.86] * 4)  # e.g. 4 imputed <LLOQ values
    assert gmt == pytest.approx(22.86) and lcl == pytest.approx(22.86) and ucl == pytest.approx(22.86)


@pytest.mark.parametrize("bad", [[0, 10], [-1, 10], [np.nan, 10]])
def test_gmt_rejects_non_positive(bad):
    with pytest.raises(ValueError):
        gmt_ci(bad)


# --- Clopper-Pearson -----------------------------------------------------------------------------------------------
# Closed forms at the edges (alpha = 0.05):
#   k = 0: LCL = 0,  UCL = 1 - (alpha/2)^(1/n)  -> n = 10: 1 - 0.025^0.1 = 0.30850
#   k = n: UCL = 1,  LCL = (alpha/2)^(1/n)      -> n = 10: 0.025^0.1 = 0.69150
def test_clopper_pearson_zero_of_n():
    lcl, ucl = clopper_pearson(0, 10)
    assert lcl == 0.0
    assert ucl == pytest.approx(1 - 0.025**0.1, abs=1e-9)
    assert sig3(ucl) == 0.308


def test_clopper_pearson_n_of_n():
    lcl, ucl = clopper_pearson(10, 10)
    assert ucl == 1.0
    assert lcl == pytest.approx(0.025**0.1, abs=1e-9)
    assert sig3(lcl) == 0.692


def test_clopper_pearson_middle_known_value():
    # 5/10, published exact 95% CI: 0.187 to 0.813
    lcl, ucl = clopper_pearson(5, 10)
    assert sig3(lcl) == 0.187 and sig3(ucl) == 0.813


def test_clopper_pearson_bad_inputs():
    assert all(math.isnan(x) for x in clopper_pearson(0, 0))
    with pytest.raises(ValueError):
        clopper_pearson(11, 10)


# --- Seroresponse (ADR 003) ----------------------------------------------------------------------------------------
LLOQ = 45.72  # assay LLOQ = 0.4572 x 100
IMPUTED = 0.5 * LLOQ  # 22.86, the analysis value of a <LLOQ result


def test_seroresponse_baseline_below_lloq_uses_4x_lloq():
    base = [IMPUTED, IMPUTED, IMPUTED]
    post = [4 * LLOQ, 4 * LLOQ - 0.01, 4 * IMPUTED]  # exactly 4xLLOQ; just under; 4-fold over imputed value only
    assert is_seroresponder(base, post, LLOQ).tolist() == [True, False, False]


def test_seroresponse_baseline_at_or_above_lloq_uses_fold_rise():
    base = [100.0, 100.0, 300.0]
    post = [400.0, 399.99, 1500.0]  # exactly 4x; just under; 5x
    assert is_seroresponder(base, post, LLOQ).tolist() == [True, False, True]


def test_seroresponse_baseline_exactly_at_lloq_is_fold_rule():
    # Baseline == LLOQ is NOT below LLOQ, so the 4-fold rule applies: post must be >= 4 x 45.72 = 182.88
    assert is_seroresponder([LLOQ, LLOQ], [4 * LLOQ, 182.87], LLOQ).tolist() == [True, False]


def test_seroresponse_fold_is_configurable():
    assert is_seroresponder([100.0], [250.0], LLOQ, fold=2.0).tolist() == [True]
    assert is_seroresponder([100.0], [250.0], LLOQ, fold=4.0).tolist() == [False]


def test_seroresponse_requires_pairs():
    with pytest.raises(ValueError):
        is_seroresponder([100.0], [400.0, 400.0], LLOQ)
