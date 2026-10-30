"""QA edge tests on a full build (seed 42) with extra problems planted by QA on top of INJ-1..8.

One module-scoped build carries all of these at once, each on its own clean plate or sample (qa_helpers.clean_plates):
  * TRUNC  a plate CSV truncated half-way (malformed upload)                  AC-4.1, AC-7.4, AC-6.2
  * FLAT   a plate where every standard reads like a blank                    AC-6.1, AC-6.2, AC-5.5
  * DUP    a second copy of a plate uploaded under another file name          AC-4.1, AC-4.4
  * GHOST  a plate-map sample ID that does not exist in the LIMS              AC-4.4, AC-7.4
  * ORDER  a custody step performed before the step that should precede it   AC-2.4
Expectation for every one: the run finishes, dbt passes, each case is caught with a reason, nothing drops silently,
and recall for the planted INJ problems stays 100%. xfail(strict) = a logged bug in docs/team/BUGS.md.
"""

from __future__ import annotations

import datetime as dt
import shutil

import duckdb
import pandas as pd
import pytest

from tests.qa.qa_helpers import clean_plates, plate_samples, read_plate, staged_build, write_plate

GHOST = "SMP-99999"


def _mutate(landing):
    trunc, flat, dup, ghost_plate, order_plate = clean_plates(landing)[:5]
    info = dict(trunc=trunc, flat=flat, dup=dup, ghost_plate=ghost_plate)
    info["trunc_samples"] = plate_samples(landing, trunc)
    info["flat_samples"] = plate_samples(landing, flat)

    f = landing / "plates" / f"{trunc}.csv"
    text = f.read_text()
    f.write_text(text[: len(text) // 2])

    # FLAT: every standard well (cols 1-2 in this layout, per plate_map) reads like a blank
    pm = pd.read_csv(landing / "plate_map.csv", dtype=str)
    std = pm[(pm.plate_id == flat) & (pm.well_type == "STD")]
    plate = read_plate(landing, flat)
    for w in std.well:
        plate.loc[w[0], w[1:]] = "0.050"
    write_plate(landing, flat, plate)

    info["dup_file"] = f"{dup} (1).csv"
    shutil.copy(landing / "plates" / f"{dup}.csv", landing / "plates" / info["dup_file"])

    # GHOST: relabel one sample's wells on the plate map with an ID the LIMS has never seen
    victim = plate_samples(landing, ghost_plate)[0]
    info["ghost_victim"] = victim
    pm.loc[(pm.plate_id == ghost_plate) & (pm.sample_id == victim), "sample_id"] = GHOST
    pm.to_csv(landing / "plate_map.csv", index=False)

    # ORDER: `received` performed (and recorded) 2 days before `collected`
    ev = pd.read_csv(landing / "custody_events.csv", dtype=str, keep_default_na=False)
    truth = pd.read_csv(landing / "injected_problems.csv", dtype=str)
    taken = set(truth.affected_key)
    s = next(x for x in plate_samples(landing, order_plate)
             if not set(ev.loc[ev.sample_id == x, "event_id"]) & taken)
    info["order_sample"] = s
    coll = ev[(ev.sample_id == s) & (ev.step == "collected")].iloc[0]
    when = (dt.datetime.fromisoformat(coll.performed_at) - dt.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    i = ev.index[(ev.sample_id == s) & (ev.step == "received")][0]
    ev.loc[i, ["performed_at", "recorded_at"]] = when
    ev.to_csv(landing / "custody_events.csv", index=False)
    return info


@pytest.fixture(scope="module")
def qa_build(tmp_path_factory):
    paths, info, dbt = staged_build(tmp_path_factory.mktemp("qa_edges"), _mutate)
    con = duckdb.connect(str(paths.db), read_only=True)
    yield {"con": con, "info": info, "dbt": dbt, "paths": paths}
    con.close()


def q(b, sql, *params):
    return b["con"].execute(sql, list(params)).df()


def test_run_finishes_and_dbt_passes(qa_build):
    assert qa_build["dbt"]["failed"] == 0, qa_build["dbt"]


def test_planted_problems_still_100pct_recall(qa_build):
    sc = q(qa_build, "select problem_id, bool_and(detected) as hit from marts.detection_scorecard group by 1")
    assert sc.hit.all(), sc[~sc.hit]


def test_every_sample_reportable_xor_missing(qa_build):
    df = q(qa_build, """select s.sample_id, f.sample_id is not null as rep, m.sample_id is not null as miss
                        from lims.samples s left join core.fct_reportable_result f using (sample_id)
                        left join core.missing_results m using (sample_id)""")
    assert (df.rep ^ df.miss).all(), df[~(df.rep ^ df.miss)]


# ---- TRUNC: malformed plate -------------------------------------------------------------------------------------

def test_truncated_plate_logged_not_crashed(qa_build):
    err = q(qa_build, "select * from assay.ingest_errors")
    assert err.file_name.str.startswith(qa_build["info"]["trunc"]).any(), err
    assert q(qa_build, "select count(*) n from assay.well_reads where plate_id = ?",
             qa_build["info"]["trunc"]).n[0] == 0


def test_truncated_plate_samples_listed_as_missing(qa_build):
    m = q(qa_build, "select sample_id, reason from core.missing_results")
    lost = set(qa_build["info"]["trunc_samples"])
    assert lost <= set(m.sample_id)


def test_truncated_plate_samples_on_reassay_list(qa_build):
    r = q(qa_build, "select distinct sample_id from core.reassay_list")
    assert set(qa_build["info"]["trunc_samples"]) <= set(r.sample_id)


# ---- FLAT: every standard fails -----------------------------------------------------------------------------------

def test_all_standards_failed_plate_rejected(qa_build):
    st = q(qa_build, "select status, reject_reasons from assay.plate_status where plate_id = ?",
           qa_build["info"]["flat"])
    assert st.status[0] == "REJECTED"
    assert {"FIT_FAIL", "STD_RECOVERY"} & set(st.reject_reasons[0].split(","))


def test_all_standards_failed_plate_has_no_working_range(qa_build):
    fit = q(qa_build, "select lloq_conc, uloq_conc from assay.curve_fits where plate_id = ?", qa_build["info"]["flat"])
    assert fit.lloq_conc.isna()[0] and fit.uloq_conc.isna()[0]


def test_all_standards_failed_samples_not_reported_and_reassayed(qa_build):
    flat, ss = qa_build["info"]["flat"], set(qa_build["info"]["flat_samples"])
    rep = q(qa_build, "select sample_id from core.fct_reportable_result where plate_id = ?", flat)
    assert rep.empty
    r = q(qa_build, "select sample_id from core.reassay_list where plate_id = ? and rule_id like '%PLATE_REJECTED%'",
          flat)
    assert set(r.sample_id) == ss


# ---- DUP: same plate uploaded twice under another name ------------------------------------------------------------

def test_duplicate_upload_does_not_double_count(qa_build):
    dup = qa_build["info"]["dup"]
    st = q(qa_build, "select plate_id from assay.plate_status where plate_id like ?", dup + "%")
    assert list(st.plate_id) == [dup]
    rep = q(qa_build, "select count(*) n from core.fct_reportable_result group by sample_id having count(*) > 1")
    assert rep.empty


def test_duplicate_upload_is_reported(qa_build):
    dup_file = qa_build["info"]["dup_file"]
    err = q(qa_build, "select file_name from assay.ingest_errors")
    assert dup_file in set(err.file_name)


# ---- GHOST: sample ID not in the LIMS ----------------------------------------------------------------------------

def test_unknown_sample_id_flagged(qa_build):
    f = q(qa_build, "select * from assay.qc_flags where rule_id = 'ID_MISMATCH' and sample_id = ?", GHOST)
    assert len(f) == 1 and f.blocking[0]


def test_unknown_sample_id_never_reported(qa_build):
    assert q(qa_build, "select * from core.fct_reportable_result where sample_id = ?", GHOST).empty


def test_displaced_lims_sample_not_silently_dropped(qa_build):
    v = qa_build["info"]["ghost_victim"]
    m = q(qa_build, "select reason from core.missing_results where sample_id = ?", v)
    assert len(m) == 1, "the LIMS sample whose wells were relabelled must be in missing_results"


# ---- ORDER: custody step out of order -----------------------------------------------------------------------------

def test_custody_out_of_order_flagged(qa_build):
    s = qa_build["info"]["order_sample"]
    f = q(qa_build, "select * from integrity.custody_flags where flag_code = 'CUSTODY_ORDER' and key = ?", s)
    assert len(f) == 1 and "received" in f.detail[0]


def test_custody_out_of_order_not_a_gap(qa_build):
    s = qa_build["info"]["order_sample"]
    assert q(qa_build, "select * from integrity.custody_flags where flag_code = 'CUSTODY_GAP' and key = ?", s).empty
