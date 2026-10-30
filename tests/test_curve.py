"""4PL fit, inverse, working range and range labels (US-5, ADR 004)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.config import load_rules
from pipeline.curve import FitResult, classify, fit_plate, four_pl, inverse_four_pl, working_range

RULES = load_rules()
LEVELS = np.array(RULES["assay"]["std_levels_au_ml"], dtype=float)
TRUE = dict(a=0.02, b=0.8, c=120.0, d=3.4)


def _std(y_fn=None):
    rows = []
    for k, x in enumerate(LEVELS, start=1):
        y = four_pl(x, **TRUE) if y_fn is None else y_fn(k, x)
        rows += [dict(level=k, nominal_conc=x, od_blank_corrected=float(y))] * 2
    return pd.DataFrame(rows)


def test_no_noise_fit_recovers_c_within_1pct():  # AC-5.2
    fit = fit_plate(_std(), RULES)
    assert fit.converged
    assert fit.c == pytest.approx(TRUE["c"], rel=0.01)
    assert fit.r_squared > 0.9999
    assert fit.recovery.within_limits.all()
    assert (fit.lloq_conc, fit.uloq_conc) == (LEVELS.min(), LEVELS.max())


def test_inverse_of_four_pl_is_identity():
    x = np.array([0.5, 3.0, 50.0, 400.0, 900.0])
    assert inverse_four_pl(four_pl(x, **TRUE), **TRUE) == pytest.approx(x, rel=1e-9)


def test_inverse_outside_asymptotes_is_nan():
    assert np.isnan(inverse_four_pl(np.array([TRUE["d"] + 0.1, TRUE["a"] - 0.01]), **TRUE)).all()


def test_non_converging_input_returns_converged_false():
    flat = fit_plate(_std(lambda k, x: np.nan), RULES)
    assert not flat.converged and flat.fit_message
    few = fit_plate(_std().head(4), RULES)
    assert not few.converged


def test_out_of_range_od_gets_labels_and_no_extrapolation():  # AC-5.4
    fit = fit_plate(_std(), RULES)
    ods = np.array([fit.lloq_od * 0.5, four_pl(10.0, **TRUE), fit.uloq_od * 1.02])
    assert list(classify(ods, fit)) == ["<LLOQ", "IN_RANGE", ">ULOQ"]
    unfit = FitResult(None, None, None, None, None, False, "x", 0, pd.DataFrame())
    assert list(classify(ods, unfit)) == [None, None, None]


def test_working_range_is_longest_contiguous_run():  # AC-5.5
    def rec(ok):
        return pd.DataFrame(dict(nominal_conc=LEVELS[::-1], within_limits=ok))
    # ascending conc order: levels 8..1. A gap at the 3rd lowest splits the run; the longer upper run wins.
    assert working_range(rec([True, True, False, True, True, True, True, True])) == (LEVELS[4], LEVELS[0])
    assert working_range(rec([False, True, True, True, True, True, True, False])) == (LEVELS[6], LEVELS[1])
    assert working_range(rec([False] * 8)) == (None, None)
    # tie: the lower-concentration run wins
    assert working_range(rec([True, True, False, False, False, False, True, True])) == (LEVELS[7], LEVELS[6])


def test_bad_standard_fails_recovery():
    fit = fit_plate(_std(lambda k, x: four_pl(x / 5 if k in (2, 4, 6) else x, **TRUE)), RULES)
    assert fit.recovery.within_limits.sum() < 6


def test_fit_stuck_at_a_bound_is_not_converged():  # review F4
    # standards that keep rising past the top level push c to its upper bound (max x * 10)
    fit = fit_plate(_std(lambda k, x: 0.002 * x), RULES)
    assert not fit.converged and "at upper bound" in fit.fit_message
    assert fit.c is not None and fit.r_squared is not None   # kept for the reviewer


def test_nan_mean_od_gets_no_label():  # review F8
    fit = fit_plate(_std(), RULES)
    assert list(classify(np.array([np.nan, four_pl(10.0, **TRUE)]), fit)) == [None, "IN_RANGE"]
