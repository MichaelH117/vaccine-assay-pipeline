"""4PL standard curve per plate, back-calculation and working range (ADR 004, US-5).

Model: y = d + (a - d) / (1 + (x / c) ** b), x = nominal concentration (curve units, AU/mL before dilution),
y = blank-corrected OD. Fit with scipy curve_fit on all standard wells, unweighted.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeWarning, curve_fit

from pipeline.schema import write_table

IN_RANGE, BELOW, ABOVE = "IN_RANGE", "<LLOQ", ">ULOQ"
BOUND_TOL = 1e-3   # relative distance to a curve_fit bound that counts as "stuck at the bound"


def four_pl(x, a, b, c, d) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return d + (a - d) / (1.0 + (np.clip(x, 0, None) / c) ** b)


def inverse_four_pl(y, a, b, c, d) -> np.ndarray:
    """x for a given y. NaN when y is outside the open interval between the asymptotes."""
    y = np.asarray(y, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        ratio = (a - d) / (y - d) - 1.0
        x = c * np.where(ratio > 0, ratio, np.nan) ** (1.0 / b)
    return np.where(np.isfinite(x), x, np.nan)


@dataclass
class FitResult:
    a: float | None
    b: float | None
    c: float | None
    d: float | None
    r_squared: float | None
    converged: bool
    fit_message: str
    n_points: int
    # level, nominal_conc, mean_od, back_calc_conc, recovery_pct, within_limits
    recovery: pd.DataFrame = field(repr=False)
    lloq_conc: float | None = None
    uloq_conc: float | None = None
    lloq_od: float | None = None
    uloq_od: float | None = None

    @property
    def params(self) -> tuple[float, float, float, float]:
        return self.a, self.b, self.c, self.d


def working_range(recovery: pd.DataFrame) -> tuple[float | None, float | None]:
    """Longest contiguous run of standard levels (ordered by concentration) with recovery within limits (AC-5.5).
    Ties go to the run with the lower concentrations. Returns (lloq_conc, uloq_conc) or (None, None)."""
    r = recovery.sort_values("nominal_conc").reset_index(drop=True)
    best, start = (0, None, None), None
    for i, ok in enumerate(list(r["within_limits"]) + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start > best[0]:
                best = (i - start, start, i - 1)
            start = None
    if best[0] == 0:
        return None, None
    return float(r.loc[best[1], "nominal_conc"]), float(r.loc[best[2], "nominal_conc"])


def fit_plate(std: pd.DataFrame, rules: dict) -> FitResult:
    """Fit one plate. `std` has one row per standard well: level, nominal_conc, od_blank_corrected.
    Never raises on bad data: a failed fit returns converged=False (gives FIT_FAIL)."""
    f = rules["fit"]
    x = std["nominal_conc"].to_numpy(float)
    y = std["od_blank_corrected"].to_numpy(float)
    rec = (std.groupby(["level", "nominal_conc"], as_index=False)["od_blank_corrected"].mean()
           .rename(columns={"od_blank_corrected": "mean_od"}).sort_values("level").reset_index(drop=True))
    fail = FitResult(None, None, None, None, None, False, "", len(x),
                     rec.assign(back_calc_conc=np.nan, recovery_pct=np.nan, within_limits=False))
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0)
    if ok.sum() < 5:
        fail.fit_message = f"too few valid standard points ({int(ok.sum())})"
        return fail
    x, y = x[ok], y[ok]
    p0 = [float(np.min(y)), 1.0, float(np.median(x)), float(np.max(y))]
    lo = [-np.inf, 0.1, float(x.min()) / 10, -np.inf]
    hi = [np.inf, 10.0, float(x.max()) * 10, np.inf]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", OptimizeWarning)
            popt, _ = curve_fit(four_pl, x, y, p0=p0, bounds=(lo, hi), maxfev=int(f["maxfev"]))
    except (RuntimeError, OptimizeWarning, ValueError) as e:
        fail.fit_message = f"{type(e).__name__}: {e}"[:200]
        return fail
    if not np.all(np.isfinite(popt)):
        fail.fit_message = "non-finite parameters"
        return fail
    a, b, c, d = (float(v) for v in popt)
    ss_res = float(np.sum((y - four_pl(x, a, b, c, d)) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # A fit that stopped on a parameter bound is not a real optimum: report it as a failed fit (FIT_FAIL), keeping
    # the parameters and R2 for the reviewer (review F4).
    def at(v, bound):
        return bool(np.isfinite(bound)) and abs(v - bound) <= BOUND_TOL * max(abs(bound), 1e-12)

    pinned = [f"{n}={v:g} at {'lower' if at(v, low) else 'upper'} bound"
              for n, v, low, high in zip("abcd", popt, lo, hi, strict=True) if at(v, low) or at(v, high)]
    if pinned:
        fail.a, fail.b, fail.c, fail.d, fail.r_squared = a, b, c, d, r2
        fail.fit_message = "parameter at bound: " + ", ".join(pinned)
        return fail

    back = inverse_four_pl(rec["mean_od"].to_numpy(float), a, b, c, d)
    rec["back_calc_conc"] = back
    rec["recovery_pct"] = back / rec["nominal_conc"].to_numpy(float) * 100
    rec["within_limits"] = rec["recovery_pct"].between(f["recovery_low_pct"], f["recovery_high_pct"])
    rec["within_limits"] = rec["within_limits"].fillna(False).astype(bool)
    lloq, uloq = working_range(rec)
    res = FitResult(a, b, c, d, r2, True, "converged", len(x), rec, lloq, uloq)
    if lloq is not None:
        res.lloq_od = float(four_pl(lloq, a, b, c, d))
        res.uloq_od = float(four_pl(uloq, a, b, c, d))
    return res


def classify(mean_od, fit: FitResult) -> np.ndarray:
    """IN_RANGE / <LLOQ / >ULOQ per mean OD against the plate's working range. None when the plate has no curve
    or no working range (no label can be given; such plates are REJECTED by QC)."""
    mean_od = np.asarray(mean_od, dtype=float)
    if not fit.converged or fit.lloq_od is None:
        return np.array([None] * len(mean_od), dtype=object)
    lo, hi = sorted([fit.lloq_od, fit.uloq_od])
    increasing = fit.uloq_od >= fit.lloq_od
    below = mean_od < lo if increasing else mean_od > hi
    above = mean_od > hi if increasing else mean_od < lo
    out = np.where(below, BELOW, np.where(above, ABOVE, IN_RANGE)).astype(object)
    out[~np.isfinite(mean_od)] = None   # a NaN OD gets no label, never IN_RANGE (review F8)
    return out


def _cv_pct(v: pd.Series) -> float:
    m = v.mean()
    return float(v.std(ddof=1) / abs(m) * 100) if len(v) > 1 and m != 0 else np.nan


def fit_all(con, rules: dict) -> int:
    """Fit every ingested plate. Writes assay.curve_fits, std_recovery, control_results, sample_results
    (all through the audit API). Returns the number of plates fitted (converged or not)."""
    wells = con.execute("""
        select w.plate_id, w.well, w.col_num, w.row_letter, w.od_blank_corrected,
               m.well_type, m.level, m.nominal_conc, m.sample_id, m.dilution, r.run_at
        from assay.well_reads w
        join assay.plate_map m using (plate_id, well)
        left join lims.plate_runs r using (plate_id)
        order by w.plate_id, w.col_num, w.row_letter
    """).df()
    fits, recs, ctrls, samples = [], [], [], []
    for plate_id, p in wells.groupby("plate_id", sort=True):
        fit = fit_plate(p[p.well_type == "STD"], rules)
        fits.append(dict(plate_id=plate_id, a=fit.a, b=fit.b, c=fit.c, d=fit.d, r_squared=fit.r_squared,
                         converged=fit.converged, fit_message=fit.fit_message, n_points=fit.n_points,
                         lloq_conc=fit.lloq_conc, uloq_conc=fit.uloq_conc, lloq_od=fit.lloq_od, uloq_od=fit.uloq_od))
        recs.append(fit.recovery.assign(plate_id=plate_id))
        for lvl in ("HIGH", "LOW"):
            od = p.loc[p.well_type == f"CTRL_{lvl}", "od_blank_corrected"]
            ctl = rules["controls"][lvl]
            target, tol = float(ctl["target_au_ml"]), float(ctl["tolerance_pct"]) / 100
            conc = float(inverse_four_pl(od.mean(), *fit.params)) if fit.converged and len(od) else np.nan
            ctrls.append(dict(plate_id=plate_id, ctrl_level=lvl, mean_conc=None if np.isnan(conc) else conc,
                              target_conc=target, low_limit=target * (1 - tol), high_limit=target * (1 + tol)))
        s = p[p.well_type == "SAMPLE"]
        if s.empty:
            continue
        g = (s.groupby("sample_id", sort=True)
             .agg(dilution=("dilution", "first"), mean_od=("od_blank_corrected", "mean"),
                  od_cv_pct=("od_blank_corrected", _cv_pct), run_at=("run_at", "first"))
             .reset_index())
        g["range_flag"] = classify(g["mean_od"], fit)
        if fit.converged:
            curve = inverse_four_pl(g["mean_od"].to_numpy(float), *fit.params)
            g["conc_au_ml"] = np.where(g["range_flag"] == IN_RANGE, curve * g["dilution"].to_numpy(float), np.nan)
        else:
            g["conc_au_ml"] = np.nan
        g["plate_id"] = plate_id
        g["result_id"] = plate_id + ":" + g["sample_id"]
        samples.append(g)

    cols_sr = ["result_id", "plate_id", "sample_id", "dilution", "mean_od", "od_cv_pct", "range_flag", "conc_au_ml",
               "run_at"]
    cols_rec = ["plate_id", "level", "nominal_conc", "mean_od", "back_calc_conc", "recovery_pct", "within_limits"]
    write_table(con, "assay.curve_fits", pd.DataFrame(fits), ["plate_id"], "4PL fit (scipy curve_fit, ADR 004)")
    if recs:
        write_table(con, "assay.std_recovery", pd.concat(recs)[cols_rec], ["plate_id", "level"],
                    "standard back-calculated recovery")
    write_table(con, "assay.control_results", pd.DataFrame(ctrls), ["plate_id", "ctrl_level"],
                "control back-calculated concentration")
    if samples:
        sr = pd.concat(samples, ignore_index=True)[cols_sr]
        sr["conc_au_ml"] = sr["conc_au_ml"].astype(float)
        write_table(con, "assay.sample_results", sr, ["result_id"], "sample back-calculation (inverse 4PL x dilution)")
    return len(fits)
