"""mart_immunogenicity: GMT/GMC, GMFR and seroresponse by group x visit (owner: LIA, US-8, ADR 003).

A dbt Python model so it can use pipeline.stats (scipy t and beta quantiles). run_dbt sets PYTHONPATH to the project
root (DESIGN R4). Rules come from dbt vars through the model config in _marts.yml: no threshold is hard-coded here.
Definitions: docs/METRICS.md.

Contract note: DESIGN 3.3 names the seroresponse denominator `sero_N`. DuckDB column names are case-insensitive, so
`sero_n` and `sero_N` would collide. The denominator is `sero_total` (requested in HANDOFF.md).
"""

import math
import os
import sys


def _import_stats():
    try:
        from pipeline import stats
    except ImportError:  # fallback if PYTHONPATH was not passed through (dbt runs from dbt/ or the root)
        for cand in (os.getcwd(), os.path.dirname(os.getcwd())):
            if os.path.isfile(os.path.join(cand, "pipeline", "stats.py")) and cand not in sys.path:
                sys.path.insert(0, cand)
        from pipeline import stats
    return stats


def _clean(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


COLS = ["group_name", "visit", "visit_day", "n", "gmt", "gmt_lcl", "gmt_ucl", "gmfr", "gmfr_lcl", "gmfr_ucl",
        "gmfr_n", "sero_n", "sero_total", "sero_pct", "sero_lcl", "sero_ucl"]
FLOAT_COLS = ["gmt", "gmt_lcl", "gmt_ucl", "gmfr", "gmfr_lcl", "gmfr_ucl", "sero_pct", "sero_lcl", "sero_ucl"]
INT_COLS = ["gmfr_n", "sero_n", "sero_total"]


def build_rows(fct, stats, conf: float, fold: float, lloq: float, baseline: str) -> list[dict]:
    """fct: one row per reportable result with subject_id, group_name, visit, visit_day, analysis_value_au_ml."""
    fct = fct[fct["analysis_value_au_ml"].notna()]
    base = fct[fct["visit"] == baseline][["subject_id", "analysis_value_au_ml"]].rename(
        columns={"analysis_value_au_ml": "base_value"}
    )
    rows = []
    for (group, visit), g in fct.groupby(["group_name", "visit"], sort=True):
        gmt, gmt_l, gmt_u = stats.gmt_ci(g["analysis_value_au_ml"].to_numpy(dtype=float), conf)
        row = dict.fromkeys(COLS)
        row.update(group_name=group, visit=visit, visit_day=int(g["visit_day"].min()), n=int(len(g)),
                   gmt=gmt, gmt_lcl=gmt_l, gmt_ucl=gmt_u)
        if visit != baseline:
            # AC-8.2: only subjects with both a baseline and a post value
            paired = g.merge(base, on="subject_id", how="inner")
            n = int(len(paired))
            row.update(gmfr_n=n, sero_n=0, sero_total=n)
            if n:
                post_v = paired["analysis_value_au_ml"].to_numpy(dtype=float)
                base_v = paired["base_value"].to_numpy(dtype=float)
                f, fl, fu = stats.gmfr_ci(post_v, base_v, conf)
                k = int(stats.is_seroresponder(base_v, post_v, lloq, fold).sum())
                sl, su = stats.clopper_pearson(k, n, conf)
                row.update(gmfr=f, gmfr_lcl=fl, gmfr_ucl=fu, sero_n=k,
                           sero_pct=100.0 * k / n, sero_lcl=100.0 * sl, sero_ucl=100.0 * su)
        rows.append({k: _clean(v) for k, v in row.items()})
    return rows


def model(dbt, session):
    import pandas as pd

    stats = _import_stats()
    conf = float(dbt.config.get("ci_level"))
    fold = float(dbt.config.get("seroresponse_fold"))
    lloq = float(dbt.config.get("assay_lloq_au_ml"))
    baseline = str(dbt.config.get("baseline_visit"))

    fct = dbt.ref("fct_reportable_result").df()
    rows = build_rows(fct, stats, conf, fold, lloq, baseline)

    out = pd.DataFrame(rows, columns=COLS)
    out[FLOAT_COLS] = out[FLOAT_COLS].astype("float64")
    for c in INT_COLS:
        out[c] = out[c].astype("Int64")
    out["group_visit_key"] = out["group_name"].astype(str) + ":" + out["visit"].astype(str)
    return out
