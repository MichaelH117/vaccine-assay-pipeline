"""QA edge tests on whole runs: unusual seeds, re-running on an existing folder, bad input that must not abort the
run, and a raw file edited after ingest. xfail(strict) = a logged bug in docs/team/BUGS.md."""

from __future__ import annotations

import os
import stat

import duckdb
import pytest

from pipeline.config import load_rules
from pipeline.ingest import make_writable
from pipeline.integrity import rehash_raw_files
from pipeline.run import LAST_DBT, build
from tests.qa.qa_helpers import clean_plates, read_plate, staged_build, write_plate

MAX_FP = float(load_rules()["scorecard"]["max_unexplained_flag_pct"])


# ---- unusual seeds ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 2, 3, 2**32 - 1, 10**12])
def test_seed_sweep_recall_and_fp(tmp_path, seed):
    paths = build(tmp_path, seed=seed, quiet=True)
    assert LAST_DBT["failed"] == 0, LAST_DBT
    with duckdb.connect(str(paths.db), read_only=True) as con:
        miss = con.execute("select problem_id, inj_type from marts.detection_scorecard group by all "
                           "having not bool_and(detected)").fetchall()
        fp = con.execute("select fp_pct from marts.scorecard_false_positives").fetchone()[0]
        n_types = con.execute("select count(distinct inj_type) from truth.injected_problems").fetchone()[0]
    assert miss == [], f"seed {seed}: missed {miss}"
    assert n_types == len(load_rules()["scorecard"]["required_inj_types"])   # INJ-11 added 2026-10-30
    assert fp <= MAX_FP, f"seed {seed}: FP {fp}%"


def test_invalid_seed_leaves_previous_data_alone(tmp_path):
    keep = tmp_path / "data" / "landing" / "previous_run.csv"
    keep.parent.mkdir(parents=True)
    keep.write_text("x\n")
    with pytest.raises(ValueError):
        build(tmp_path, seed=-1, quiet=True)
    assert keep.exists()


# ---- re-run on an existing folder / DB ----------------------------------------------------------------------------

def _snapshot(paths):
    with duckdb.connect(str(paths.db), read_only=True) as con:
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0]
                for t in ("lims.samples", "assay.well_reads", "assay.qc_flags", "core.fct_reportable_result",
                          "core.missing_results", "core.reassay_list", "audit.audit_log")} | {
            "chain": con.execute("select ok, first_broken_seq from audit.chain_verify").fetchall(),
            "hash_ok": con.execute("select bool_and(matches) from audit.file_integrity").fetchone()[0]}


def test_rerun_on_existing_folder_gives_same_result(tmp_path):
    first = _snapshot(build(tmp_path, seed=42, quiet=True))
    paths = build(tmp_path, seed=42, quiet=True)   # raw copies from run 1 are read-only (DESIGN R6)
    assert LAST_DBT["failed"] == 0
    assert _snapshot(paths) == first
    assert all(not os.access(p, os.W_OK) for p in paths.raw.glob("*.csv"))


def test_raw_file_edited_after_ingest_caught_then_rebuild_restores(tmp_path):
    paths = build(tmp_path, seed=42, quiet=True)
    victim = sorted(paths.raw.glob("*.csv"))[0]
    os.chmod(victim, stat.S_IWRITE | stat.S_IREAD)
    victim.write_text(victim.read_text().replace("0.", "0.9", 1))
    with duckdb.connect(str(paths.db)) as con:
        assert rehash_raw_files(con, paths.raw) == 1
        bad = con.execute("select file_name from audit.file_integrity where not matches").fetchall()
    assert bad == [(victim.name,)]
    # deleting the raw copy is also a mismatch
    os.remove(victim)
    with duckdb.connect(str(paths.db)) as con:
        assert rehash_raw_files(con, paths.raw) == 1
    make_writable(paths.raw)
    paths = build(tmp_path, seed=42, quiet=True)
    assert _snapshot(paths)["hash_ok"] is True


# ---- bad plate content must not abort the run ---------------------------------------------------------------------

def _set_cell(value):
    def mutate(landing):
        pid = clean_plates(landing)[0]
        p = read_plate(landing, pid)
        p.loc["A", "5"] = value   # a sample well in this layout
        write_plate(landing, pid, p)
        return {"plate": pid}
    return mutate


def test_infinite_od_does_not_abort_run(tmp_path):
    paths, info, _ = staged_build(tmp_path, _set_cell("inf"), with_dbt=False)
    with duckdb.connect(str(paths.db), read_only=True) as con:
        assert con.execute("select count(*) from assay.ingest_errors where file_name like ?",
                           [info["plate"] + "%"]).fetchone()[0] == 1


def test_all_blank_plate_rejected_without_crash(tmp_path):
    def mutate(landing):
        pid = clean_plates(landing)[0]
        p = read_plate(landing, pid)
        p.loc[:, :] = "0.050"
        write_plate(landing, pid, p)
        return {"plate": pid}
    paths, info, _ = staged_build(tmp_path, mutate, with_dbt=False)
    with duckdb.connect(str(paths.db), read_only=True) as con:
        st = con.execute("select status from assay.plate_status where plate_id = ?", [info["plate"]]).fetchone()
        rep = con.execute("select count(*) from assay.reportable_selection r join assay.sample_results s "
                          "on r.result_id = s.result_id where s.plate_id = ?", [info["plate"]]).fetchone()[0]
    assert st == ("REJECTED",) and rep == 0


def test_empty_plate_file_logged_and_run_continues(tmp_path):
    def mutate(landing):
        pid = clean_plates(landing)[0]
        (landing / "plates" / f"{pid}.csv").write_text("")
        return {"plate": pid}
    paths, info, dbt = staged_build(tmp_path, mutate)
    assert dbt["failed"] == 0
    with duckdb.connect(str(paths.db), read_only=True) as con:
        err = con.execute("select error from assay.ingest_errors").fetchall()
        n_status = con.execute("select count(*) from assay.plate_status").fetchone()[0]
        st = con.execute("select status, reject_reasons from assay.plate_status where plate_id = ?",
                         [info["plate"]]).fetchone()
    assert len(err) == 1 and "unreadable" in err[0][0]
    # BUG-003 fix (data-engineer, 2026-10-30): the unreadable plate stays visible as REJECTED / INGEST_ERROR
    assert n_status == 13 and st == ("REJECTED", "INGEST_ERROR")
