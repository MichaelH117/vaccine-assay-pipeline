"""Reportable result per sample: the latest valid run (ADR 006, AC-7.2).

A run is valid when its plate is ACCEPTED, the sample has no blocking flag on that plate, and the result is IN_RANGE
or <LLOQ. Every LIMS sample gets one assay.reportable_selection row (REPORTABLE or NO_VALID_RESULT), written through
the audit API with the reason, so the choice is in the audit trail.
"""

from __future__ import annotations

import pandas as pd

from pipeline.schema import write_table


def _why_not(r) -> str:
    if r.status != "ACCEPTED":
        return f"{r.plate_id} rejected ({r.reject_reasons})"
    if r.blocking_rules:
        return f"{r.plate_id} {r.blocking_rules}"
    if r.range_flag not in ("IN_RANGE", "<LLOQ"):
        return f"{r.plate_id} no usable result ({r.range_flag})"
    return f"{r.plate_id} earlier valid run"


def choose(runs: pd.DataFrame, samples: list[str]) -> pd.DataFrame:
    """Pure: one decision per sample. `runs` has result_id, sample_id, plate_id, run_at, range_flag, status,
    reject_reasons, blocking_rules ('' if none).

    Grouped, not scanned per sample (the per-sample filter took 221 s at 100x): sort once, compute every run's
    validity and "why not" text once, bucket the runs by sample in one pass, then walk each bucket.
    Output is identical to the old loop
    (tests/test_reportable.py compares them on the seed-42 build)."""
    r = runs.sort_values(["sample_id", "run_at", "plate_id"], kind="mergesort").reset_index(drop=True)
    valid = ((r.status == "ACCEPTED") & (r.blocking_rules == "") & r.range_flag.isin(["IN_RANGE", "<LLOQ"])).tolist()
    why = [_why_not(x) for x in r.itertuples()]
    groups: dict[str, list[tuple]] = {}
    for row in zip(r.sample_id, r.plate_id, r.result_id, valid, why, strict=True):
        groups.setdefault(row[0], []).append(row)
    out = []
    for sid in samples:
        g = groups.get(sid, [])
        n = len(g)
        if n == 0:
            out.append(dict(sample_id=sid, result_id=None, decision="NO_VALID_RESULT",
                            reason="no assay run for this sample", n_runs=0))
            continue
        ok = [x for x in g if x[3]]
        if not ok:
            out.append(dict(sample_id=sid, result_id=None, decision="NO_VALID_RESULT",
                            reason=f"no valid run of {n}; " + "; ".join(x[4] for x in g), n_runs=n))
            continue
        pick = ok[-1]
        others = [x[4] for x in g if x[1] != pick[1]]
        reason = f"latest valid run of {n}" + ("; " + "; ".join(others) if others else "")
        out.append(dict(sample_id=sid, result_id=pick[2], decision="REPORTABLE", reason=reason, n_runs=n))
    return pd.DataFrame(out)


def load_runs(con) -> pd.DataFrame:
    """One row per plate-map sample (not per result), so a sample on a plate whose file was rejected still counts as
    a failed run (BUG-003). Blocking flags are aggregated once and joined (no correlated subquery)."""
    return con.execute("""
        with mapped as (select distinct plate_id, sample_id from assay.plate_map where well_type = 'SAMPLE'),
        blocking as (
            select plate_id, sample_id, string_agg(distinct rule_id, ',' order by rule_id) as blocking_rules
            from assay.qc_flags where blocking and sample_id is not null group by plate_id, sample_id
        )
        select r.result_id, m.sample_id, m.plate_id, pr.run_at, coalesce(r.range_flag, 'NO_CURVE') as range_flag,
               p.status, p.reject_reasons, coalesce(b.blocking_rules, '') as blocking_rules
        from mapped m
        join assay.plate_status p using (plate_id)
        join lims.plate_runs pr using (plate_id)
        left join assay.sample_results r on r.plate_id = m.plate_id and r.sample_id = m.sample_id
        left join blocking b on b.plate_id = m.plate_id and b.sample_id = m.sample_id
        order by m.sample_id, pr.run_at, m.plate_id
    """).df()


def select_reportable(con) -> int:
    """Write assay.reportable_selection for every LIMS sample. Returns the number of REPORTABLE samples."""
    runs = load_runs(con)
    samples = [s for (s,) in con.execute("select sample_id from lims.samples order by sample_id").fetchall()]
    sel = choose(runs, samples)
    write_table(con, "assay.reportable_selection", sel, ["sample_id"], "reportable run selection (ADR 006)")
    return int((sel.decision == "REPORTABLE").sum())
