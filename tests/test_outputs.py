"""End-to-end outputs of the full build: tie-outs, reportable vs missing, re-runs (US-7, US-12)."""

from __future__ import annotations

import pandas as pd

from pipeline.config import dbt_vars, load_rules

LIMS = ("users", "subjects", "samples", "aliquots", "custody_events", "plate_runs")


def test_dbt_vars_has_every_dbt_key():  # DE-01
    v = dbt_vars(load_rules())
    need = {"rule_version", "assay_lloq_au_ml", "lloq_impute_factor", "custody_steps", "max_freeze_thaw",
            "late_entry_hours", "seroresponse_fold", "ci_level", "baseline_visit", "expected_flags"}
    assert need <= set(v)
    assert v["rule_version"] == load_rules()["version"]
    assert {f"INJ-{i}" for i in range(1, 9)} <= set(v["expected_flags"])


def test_load_rules_checks_the_assay_lloq(tmp_path):  # review F12
    import pytest
    import yaml

    from pipeline.config import CONFIG_PATH
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    cfg["assay"]["assay_lloq_au_ml"] = 50.0
    bad = tmp_path / "rules.yaml"
    bad.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match="lowest standard"):
        load_rules(bad)


def test_negative_seed_rejected_before_cleanup(tmp_path):  # BUG-007
    import pytest

    from pipeline.run import build
    keep = tmp_path / "data" / "raw" / "x.csv"
    keep.parent.mkdir(parents=True)
    keep.write_text("x")
    with pytest.raises(ValueError, match="non-negative"):
        build(tmp_path, seed=-1, quiet=True)
    assert keep.exists()


def test_landing_rows_tie_out_to_lims_and_staging(built):
    con, landing = built["con"], built["paths"].landing
    for t in LIMS:
        n_csv = len(pd.read_csv(landing / f"{t}.csv"))
        assert n_csv == con.execute(f"select count(*) from lims.{t}").fetchone()[0] \
            == con.execute(f"select count(*) from staging.stg_{t}").fetchone()[0], t
    n_plates = len(list((landing / "plates").glob("*.csv")))
    assert con.execute("select count(*) from staging.stg_well_reads").fetchone()[0] == 96 * n_plates


def test_every_sample_in_reportable_or_missing_never_both(built):  # AC-7.4
    con = built["con"]
    samples = {s for (s,) in con.execute("select sample_id from lims.samples").fetchall()}
    rep = {s for (s,) in con.execute("select sample_id from core.fct_reportable_result").fetchall()}
    mis = {s for (s,) in con.execute("select sample_id from core.missing_results").fetchall()}
    assert not rep & mis and rep | mis == samples


def test_inj2_samples_are_missing_with_reason(built):
    con, truth = built["con"], built["truth"]
    swap = set(truth.loc[truth.inj_type == "INJ-2", "affected_key"])
    got = dict(con.execute("select sample_id, reason from core.missing_results").fetchall())
    assert {s: got.get(s) for s in swap} == {s: "ID_MISMATCH_UNRESOLVED" for s in swap}


def test_reportable_only_from_accepted_plates_without_blocking_flags(built):  # AC-7.1
    bad = built["con"].execute("""
        select f.sample_id from core.fct_reportable_result f
        join assay.plate_status p using (plate_id)
        left join assay.qc_flags q on q.plate_id = f.plate_id and q.sample_id = f.sample_id and q.blocking
        where p.status <> 'ACCEPTED' or q.flag_id is not null""").fetchall()
    assert bad == []


def test_below_lloq_imputation(built):  # AC-7.3
    rules = load_rules()["assay"]
    rows = built["con"].execute("""select reported_value, conc_au_ml, analysis_value_au_ml
                                   from core.fct_reportable_result where below_lloq""").fetchall()
    assert rows
    for rep, conc, val in rows:
        assert rep == "<LLOQ" and conc is None
        assert val == rules["lloq_impute_factor"] * rules["assay_lloq_au_ml"]


def test_inj8_reassay_at_higher_dilution_then_reported(built):  # AC-6.4
    con, truth = built["con"], built["truth"]
    inj8 = set(truth.loc[truth.inj_type == "INJ-8", "affected_key"])
    rows = con.execute("select sample_id, rule_id, suggested_dilution, resolved from core.reassay_list "
                       "where rule_id like '%ABOVE_ULOQ%'").fetchall()
    assert {r[0] for r in rows} == inj8
    assert all(r[2] == 1000 and r[3] for r in rows)
    rep = dict(con.execute("select sample_id, dilution from core.fct_reportable_result").fetchall())
    assert all(rep[s] == 1000 for s in inj8)


def test_rejected_plate_samples_on_reassay_list(built):  # AC-6.2
    left = built["con"].execute("""
        select r.sample_id from assay.sample_results r join assay.plate_status p using (plate_id)
        where p.status = 'REJECTED'
        except select sample_id from core.reassay_list where rule_id like '%PLATE_REJECTED%'""").fetchall()
    assert left == []


def test_audit_chain_broken_only_by_inj7(built, clean_built):
    con, truth = built["con"], built["truth"]
    cv = con.execute("select ok, broken_record_key from audit.chain_verify").fetchone()
    assert cv == (False, truth.loc[truth.inj_type == "INJ-7", "affected_key"].item())
    assert clean_built["con"].execute("select ok from audit.chain_verify").fetchone()[0] is True


def test_clean_build_marts_show_vaccine_effect(clean_built):  # AC-1.4 on the pipeline output
    df = clean_built["con"].execute("select group_name, visit, gmt, gmfr from marts.mart_immunogenicity").df() \
        .set_index(["group_name", "visit"])
    assert df.loc[("Vaccine", "D29"), "gmt"] >= 4 * df.loc[("Vaccine", "D1"), "gmt"]
    assert 0.8 <= df.loc[("Placebo", "D29"), "gmfr"] <= 1.25


def test_rebuild_is_deterministic(built, tmp_path):
    """Same seed, second build: every core and mart table is identical (timestamps of the run itself excluded)."""
    import duckdb

    from pipeline.run import build
    other = duckdb.connect(str(build(tmp_path, seed=42, quiet=True).db), read_only=True)
    try:
        for t in ("core.fct_reportable_result", "core.missing_results", "core.reassay_list",
                  "marts.mart_immunogenicity", "marts.mart_lab_kpis", "marts.mart_plate_qc",
                  "marts.detection_scorecard", "marts.scorecard_false_positives", "assay.qc_flags",
                  "assay.sample_results"):
            a = built["con"].execute(f"select * from {t}").df()
            b = other.execute(f"select * from {t}").df()
            key = list(a.columns)
            pd.testing.assert_frame_equal(a.sort_values(key).reset_index(drop=True),
                                          b.sort_values(key).reset_index(drop=True), obj=t)
    finally:
        other.close()
