"""Plate and sample QC rules with reason codes, and plate accept/reject (US-6).

Plate rules (any one rejects the plate): FIT_FAIL, STD_RECOVERY, CTRL_OOR, BLANK_HIGH, and INGEST_ERROR for a
planned plate whose file was rejected or never arrived (BUG-003). CTRL_OOR is not raised on a FIT_FAIL plate: with no
trustworthy curve the control cannot be judged, and a cascaded flag would hide the real cause (review F3).
Sample rules: DUP_CV (every plate: it is computed on OD and needs no curve), BELOW_LLOQ and ABOVE_ULOQ (ACCEPTED
plates only: on a rejected plate the curve is not trusted, and every sample goes to the re-assay list anyway).
ID_MISMATCH is written by pipeline/ingest.py. Every flag carries rule_version, measured_value and threshold (AC-6.5).
Blocking: every plate flag, DUP_CV, ABOVE_ULOQ, ID_MISMATCH. BELOW_LLOQ is not blocking (reportable as <LLOQ).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.schema import write_table

PLATE_RULES = ("INGEST_ERROR", "FIT_FAIL", "STD_RECOVERY", "CTRL_OOR", "BLANK_HIGH")


def _flag(rows, rule, level, plate_id, sample_id, measured, threshold, blocking, message, sub=None):
    key = sub if sub is not None else (sample_id or "-")
    rows.append(dict(flag_id=f"{rule}:{plate_id}:{key}", level=level, plate_id=plate_id, sample_id=sample_id,
                     rule_id=rule, measured_value=None if measured is None or pd.isna(measured) else float(measured),
                     threshold=threshold, blocking=blocking, message=message))


def plate_flags(fits: pd.DataFrame, rec: pd.DataFrame, ctrl: pd.DataFrame, blanks: pd.DataFrame,
                rules: dict) -> list[dict]:
    """Pure: plate-level flags from the curve fit, standard recovery, controls and blank ODs."""
    f, rows = rules["fit"], []
    min_r2, min_pass = float(f["min_r_squared"]), float(f["min_std_pass_fraction"])
    max_blank = float(rules["plate"]["max_mean_blank_od"])
    fit_failed: set[str] = set()
    for r in fits.itertuples():
        if not r.converged or r.r_squared is None or pd.isna(r.r_squared) or r.r_squared < min_r2:
            msg = f"fit did not converge: {r.fit_message}" if not r.converged else f"R2 {r.r_squared:.4f} < {min_r2}"
            fit_failed.add(r.plate_id)
            _flag(rows, "FIT_FAIL", "PLATE", r.plate_id, None, r.r_squared,
                  f">={min_r2}", True, msg)
        pr = rec[rec.plate_id == r.plate_id]
        frac = float(pr.within_limits.astype(bool).sum()) / len(pr) if len(pr) else 0.0
        if frac < min_pass:
            _flag(rows, "STD_RECOVERY", "PLATE", r.plate_id, None, frac, f">={min_pass}", True,
                  f"{int(pr.within_limits.astype(bool).sum())} of {len(pr)} standard levels within "
                  f"{f['recovery_low_pct']}-{f['recovery_high_pct']}% recovery")
    for c in ctrl.itertuples():
        if c.plate_id in fit_failed:
            continue
        mc = c.mean_conc
        if mc is None or pd.isna(mc) or mc < c.low_limit or mc > c.high_limit:
            shown = "not computable" if mc is None or pd.isna(mc) else f"{mc:.2f}"
            _flag(rows, "CTRL_OOR", "PLATE", c.plate_id, None, mc, f"{c.low_limit:g}-{c.high_limit:g}", True,
                  f"control {c.ctrl_level} back-calculated {shown} AU/mL, target {c.target_conc:g}",
                  sub=c.ctrl_level)
    for b in blanks.itertuples():
        if b.mean_blank_od > max_blank:
            _flag(rows, "BLANK_HIGH", "PLATE", b.plate_id, None, b.mean_blank_od, f"<={max_blank}", True,
                  f"mean blank OD {b.mean_blank_od:.3f} > {max_blank}")
    return rows


def sample_flags(sr: pd.DataFrame, accepted: set[str], rules: dict) -> list[dict]:
    """Pure: DUP_CV on every plate; BELOW_LLOQ / ABOVE_ULOQ on accepted plates (see module docstring)."""
    rows = []
    max_cv = float(rules["sample"]["max_dup_cv_pct"])
    lloq = float(rules["assay"]["assay_lloq_au_ml"])
    for s in sr.itertuples():
        if pd.notna(s.od_cv_pct) and s.od_cv_pct > max_cv:
            _flag(rows, "DUP_CV", "SAMPLE", s.plate_id, s.sample_id, s.od_cv_pct, f"<={max_cv}", True,
                  f"duplicate OD CV {s.od_cv_pct:.1f}% > {max_cv}%")
        if s.plate_id not in accepted:
            continue
        if s.range_flag == "<LLOQ" or (s.range_flag == "IN_RANGE" and s.conc_au_ml < lloq):
            _flag(rows, "BELOW_LLOQ", "SAMPLE", s.plate_id, s.sample_id, s.conc_au_ml, f">={lloq}", False,
                  "signal below the plate working range" if s.range_flag == "<LLOQ"
                  else f"{s.conc_au_ml:.1f} AU/mL below assay LLOQ {lloq}")
        elif s.range_flag == ">ULOQ":
            _flag(rows, "ABOVE_ULOQ", "SAMPLE", s.plate_id, s.sample_id, s.mean_od, "<=ULOQ OD", True,
                  f"mean OD {s.mean_od:.3f} above the plate ULOQ at 1:{s.dilution}")
    return rows


def run_qc(con, rules: dict) -> dict[str, int]:
    """Apply every rule, write assay.qc_flags and assay.plate_status. Returns flag counts by rule."""
    fits = con.execute("select * from assay.curve_fits order by plate_id").df()
    rec = con.execute("select * from assay.std_recovery order by plate_id, level").df()
    ctrl = con.execute("select * from assay.control_results order by plate_id, ctrl_level").df()
    blanks = con.execute("""
        select w.plate_id, avg(w.od) as mean_blank_od from assay.well_reads w
        join assay.plate_map m using (plate_id, well) where m.well_type = 'BLANK'
        group by w.plate_id order by w.plate_id""").df()
    runs = con.execute("select plate_id, run_at from lims.plate_runs order by plate_id").df()
    errors = dict(con.execute(r"select regexp_replace(file_name, '\.csv$', ''), error from assay.ingest_errors")
                  .fetchall())

    pflags = []
    for pid in sorted(set(runs.plate_id) - set(fits.plate_id)):   # planned plate with no usable reads (BUG-003)
        _flag(pflags, "INGEST_ERROR", "PLATE", pid, None, None, "plate file parsed", True,
              errors.get(pid, f"no plate file received for {pid}"))
    pflags += plate_flags(fits, rec, ctrl, blanks, rules)
    rejected: dict[str, list[str]] = {}
    for fl in pflags:
        rejected.setdefault(fl["plate_id"], [])
        if fl["rule_id"] not in rejected[fl["plate_id"]]:
            rejected[fl["plate_id"]].append(fl["rule_id"])
    status = runs.copy()
    status["status"] = np.where(status.plate_id.isin(rejected), "REJECTED", "ACCEPTED")
    status["reject_reasons"] = [",".join(sorted(rejected.get(p, []), key=PLATE_RULES.index)) for p in status.plate_id]
    accepted = set(status.loc[status.status == "ACCEPTED", "plate_id"])

    sr = con.execute("select * from assay.sample_results order by plate_id, sample_id").df()
    flags = pd.DataFrame(pflags + sample_flags(sr, accepted, rules))
    if not flags.empty:
        flags.insert(5, "rule_version", rules["version"])
        write_table(con, "assay.qc_flags", flags, ["flag_id"], f"QC rules {rules['version']}")
    write_table(con, "assay.plate_status", status[["plate_id", "status", "reject_reasons", "run_at"]], ["plate_id"],
                "plate accept/reject from plate-level QC flags")
    counts = flags.rule_id.value_counts().to_dict() if not flags.empty else {}
    counts["plates_rejected"] = len(rejected)
    return {k: int(v) for k, v in sorted(counts.items())}
