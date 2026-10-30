"""Reportable-run selection (ADR 006, AC-7.2)."""

from __future__ import annotations

import pandas as pd

from pipeline.reportable import choose


def _runs(*rows):
    cols = ["result_id", "sample_id", "plate_id", "run_at", "range_flag", "status", "reject_reasons", "blocking_rules"]
    return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows], columns=cols)


T1, T2 = pd.Timestamp("2026-04-10 09:00"), pd.Timestamp("2026-04-18 09:00")


def test_latest_valid_run_wins_with_reason():
    r = _runs(("P1:S", "S", "P1", T1, "IN_RANGE", "REJECTED", "CTRL_OOR", ""),
              ("P2:S", "S", "P2", T2, "IN_RANGE", "ACCEPTED", "", ""))
    out = choose(r, ["S"]).iloc[0]
    assert out.result_id == "P2:S" and out.decision == "REPORTABLE" and out.n_runs == 2
    assert out.reason == "latest valid run of 2; P1 rejected (CTRL_OOR)"


def test_later_invalid_run_does_not_replace_earlier_valid_run():
    r = _runs(("P1:S", "S", "P1", T1, "IN_RANGE", "ACCEPTED", "", ""),
              ("P2:S", "S", "P2", T2, ">ULOQ", "ACCEPTED", "", "ABOVE_ULOQ"))
    out = choose(r, ["S"]).iloc[0]
    assert out.result_id == "P1:S"


def test_below_lloq_is_reportable_but_blocked_flags_are_not():
    r = _runs(("P1:S", "S", "P1", T1, "<LLOQ", "ACCEPTED", "", ""),
              ("P1:X", "X", "P1", T1, "IN_RANGE", "ACCEPTED", "", "ID_MISMATCH"))
    out = choose(r, ["S", "X", "Z"]).set_index("sample_id")
    assert out.loc["S", "decision"] == "REPORTABLE"
    assert out.loc["X", "decision"] == "NO_VALID_RESULT" and "ID_MISMATCH" in out.loc["X", "reason"]
    assert out.loc["Z", "decision"] == "NO_VALID_RESULT" and out.loc["Z", "n_runs"] == 0


def test_selection_is_in_the_audit_trail(built):  # AC-7.2
    con = built["con"]
    n = con.execute("select count(*) from assay.reportable_selection").fetchone()[0]
    a = con.execute("select count(*) from audit.audit_log where table_name = 'assay.reportable_selection' "
                    "and action = 'INSERT' and reason <> ''").fetchone()[0]
    assert n == a == con.execute("select count(*) from lims.samples").fetchone()[0]
    reasons = [r for (r,) in con.execute("select reason from assay.reportable_selection where n_runs > 1").fetchall()]
    assert reasons and all(r.startswith("latest valid run of") or r.startswith("no valid run") for r in reasons)


def test_every_repeated_sample_was_on_the_reassay_list(built):  # ADR 006 link
    con = built["con"]
    missing = con.execute("""
        select distinct m.sample_id from assay.plate_map m join lims.plate_runs r using (plate_id)
        where r.repeat_of_plate_id is not null and m.well_type = 'SAMPLE'
          and m.sample_id not in (select sample_id from core.reassay_list)""").fetchall()
    assert missing == []


# ---- equivalence: grouped implementation == the old per-sample scan (perf fix, Director flaw hunt) ----------------

_OLD_RUNS_SQL = """
    with mapped as (select distinct plate_id, sample_id from assay.plate_map where well_type = 'SAMPLE')
    select r.result_id, m.sample_id, m.plate_id, pr.run_at, coalesce(r.range_flag, 'NO_CURVE') as range_flag,
           p.status, p.reject_reasons,
           coalesce((select string_agg(distinct f.rule_id, ',' order by f.rule_id) from assay.qc_flags f
                     where f.plate_id = m.plate_id and f.sample_id = m.sample_id and f.blocking), '')
               as blocking_rules
    from mapped m
    join assay.plate_status p using (plate_id)
    join lims.plate_runs pr using (plate_id)
    left join assay.sample_results r on r.plate_id = m.plate_id and r.sample_id = m.sample_id
    order by m.sample_id, pr.run_at, m.plate_id
"""


def _old_choose(runs, samples):
    """The pre-2026-10-30 implementation, kept verbatim as the reference (O(samples x runs))."""
    from pipeline.reportable import _why_not
    out = []
    for sid in samples:
        r = runs[runs.sample_id == sid].sort_values(["run_at", "plate_id"])
        valid = r[(r.status == "ACCEPTED") & (r.blocking_rules == "") & r.range_flag.isin(["IN_RANGE", "<LLOQ"])]
        n = len(r)
        if n == 0:
            out.append(dict(sample_id=sid, result_id=None, decision="NO_VALID_RESULT",
                            reason="no assay run for this sample", n_runs=0))
            continue
        if valid.empty:
            out.append(dict(sample_id=sid, result_id=None, decision="NO_VALID_RESULT",
                            reason=f"no valid run of {n}; " + "; ".join(_why_not(x) for x in r.itertuples()),
                            n_runs=n))
            continue
        pick = valid.iloc[-1]
        others = [_why_not(x) for x in r.itertuples() if x.plate_id != pick.plate_id]
        reason = f"latest valid run of {n}" + ("; " + "; ".join(others) if others else "")
        out.append(dict(sample_id=sid, result_id=pick.result_id, decision="REPORTABLE", reason=reason, n_runs=n))
    return pd.DataFrame(out)


def test_grouped_selection_matches_old_scan_on_seed_42(tmp_path):
    import duckdb

    from pipeline.reportable import load_runs
    from tests.qa.qa_helpers import staged_build
    paths, _, _ = staged_build(tmp_path, with_dbt=False)   # Python steps only, seed 42, all INJ planted
    with duckdb.connect(str(paths.db), read_only=True) as con:
        new_runs = load_runs(con)
        old_runs = con.execute(_OLD_RUNS_SQL).df()
        samples = [s for (s,) in con.execute("select sample_id from lims.samples order by sample_id").fetchall()]
        stored = con.execute("select * from assay.reportable_selection order by sample_id").df()
    pd.testing.assert_frame_equal(new_runs, old_runs)
    old, new = _old_choose(old_runs, samples), choose(new_runs, samples)
    pd.testing.assert_frame_equal(new, old)
    assert (old.n_runs > 1).sum() > 0 and (old.decision == "NO_VALID_RESULT").sum() > 0   # the hard cases exist
    assert stored.astype(object).where(stored.notna(), None).equals(new.astype(object).where(new.notna(), None))
