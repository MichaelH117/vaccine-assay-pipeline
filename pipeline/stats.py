"""Immunogenicity statistics: pure functions on numpy arrays, no database (owner: LIA).

Definitions live in docs/METRICS.md. Rules come from ADR 003:
- GMT/GMC: geometric mean of the analysis values (AU/mL). The CI is t-based on log10 values.
- GMFR: geometric mean of each subject's post / baseline ratio, with the same t-based CI.
- Seroresponse: baseline < LLOQ -> responder when post >= fold x LLOQ;
  baseline >= LLOQ -> responder when post / baseline >= fold.
- Proportion CI: exact Clopper-Pearson (beta quantiles).

Every input is an analysis value, so <LLOQ results are already imputed (0.5 x assay LLOQ) upstream.
Groups with n < 2 get a point estimate but NaN confidence limits (no degrees of freedom).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats as _st

# Relative tolerance for the ">= fold" comparisons, so 4 x 45.72 computed in floating point still counts as 4-fold.
_REL_TOL = 1e-9


def _positive_array(values, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size and (not np.all(np.isfinite(arr)) or np.any(arr <= 0)):
        raise ValueError(f"{name} must be finite and > 0 (impute <LLOQ before calling)")
    return arr


def _geo_mean_ci(arr: np.ndarray, conf: float) -> tuple[float, float, float]:
    n = arr.size
    if n == 0:
        return (math.nan, math.nan, math.nan)
    logs = np.log10(arr)
    mean = float(logs.mean())
    point = 10.0**mean
    if n < 2:
        return (point, math.nan, math.nan)
    se = float(logs.std(ddof=1)) / math.sqrt(n)
    half = float(_st.t.ppf((1.0 + conf) / 2.0, n - 1)) * se
    return (point, 10.0 ** (mean - half), 10.0 ** (mean + half))


def gmt_ci(values, conf: float = 0.95) -> tuple[float, float, float]:
    """Geometric mean titer/concentration with a t-based CI on log10 values. Returns (gmt, lcl, ucl)."""
    return _geo_mean_ci(_positive_array(values, "values"), conf)


def gmfr_ci(post, base, conf: float = 0.95) -> tuple[float, float, float]:
    """Geometric mean fold rise of paired post/base values (same subject order). Returns (gmfr, lcl, ucl)."""
    p = _positive_array(post, "post")
    b = _positive_array(base, "base")
    if p.size != b.size:
        raise ValueError("post and base must be paired (same length, same subject order)")
    return _geo_mean_ci(p / b, conf)


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Exact binomial CI for k successes out of n, as proportions in [0, 1]. Returns (lcl, ucl)."""
    if n <= 0:
        return (math.nan, math.nan)
    if k < 0 or k > n:
        raise ValueError("need 0 <= k <= n")
    alpha = 1.0 - conf
    lcl = 0.0 if k == 0 else float(_st.beta.ppf(alpha / 2.0, k, n - k + 1))
    ucl = 1.0 if k == n else float(_st.beta.ppf(1.0 - alpha / 2.0, k + 1, n - k))
    return (lcl, ucl)


def is_seroresponder(base, post, lloq: float, fold: float = 4.0) -> np.ndarray:
    """Per-subject seroresponse flag (ADR 003). A baseline exactly at LLOQ counts as >= LLOQ (fold-rise rule)."""
    b = _positive_array(base, "base")
    p = _positive_array(post, "post")
    if b.size != p.size:
        raise ValueError("base and post must be paired (same length, same subject order)")
    if lloq <= 0 or fold <= 0:
        raise ValueError("lloq and fold must be > 0")
    tol = 1.0 - _REL_TOL
    below = b < lloq
    return np.where(below, p >= fold * lloq * tol, p >= fold * b * tol)
