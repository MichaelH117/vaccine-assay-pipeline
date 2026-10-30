"""Generator: reproducibility, manifest coverage, clean-data effect sizes, synthetic IDs (US-1)."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from generator.generate import file_hashes, generate, sample_wells, write
from pipeline.config import load_rules


def test_same_seed_gives_byte_identical_files(tmp_path):  # AC-1.1
    write(generate(42), tmp_path / "a")
    write(generate(42), tmp_path / "b")
    ha, hb = file_hashes(tmp_path / "a"), file_hashes(tmp_path / "b")
    assert ha and ha == hb


def test_different_seed_changes_data(tmp_path):
    write(generate(42), tmp_path / "a")
    write(generate(7), tmp_path / "b")
    assert file_hashes(tmp_path / "a")["samples.csv"] != file_hashes(tmp_path / "b")["samples.csv"]


def test_files_use_lf_line_endings(tmp_path):
    write(generate(42), tmp_path)
    for p in tmp_path.rglob("*.csv"):
        assert b"\r\n" not in p.read_bytes(), p.name


def test_every_required_inj_type_is_in_the_manifest():  # AC-1.3
    m = generate(42).injected_problems
    sc = load_rules()["scorecard"]
    required = set(sc["required_inj_types"])
    assert required == set(m.inj_type)                       # every required type, and nothing optional by default
    assert required <= set(sc["expected_flags"])             # each one has a detecting flag in the config
    assert m.problem_id.str.fullmatch(r"P-\d{3}").all()
    # INJ-2 is one problem with two keys; every other problem has one key
    per = m.groupby("problem_id").size()
    assert (per[m[m.inj_type == "INJ-2"].problem_id.iloc[0]] == 2) and (per.drop(
        m[m.inj_type == "INJ-2"].problem_id.iloc[0]) == 1).all()


def test_optional_problems_add_inj_9_and_10():
    s = generate(42, optional_problems=True)
    m = s.injected_problems
    optional = set(load_rules()["scorecard"]["expected_flags"]) - set(load_rules()["scorecard"]["required_inj_types"])
    assert optional == {"INJ-9", "INJ-10"} and optional <= set(m.inj_type)
    a9 = m.loc[m.inj_type == "INJ-9", "affected_key"].item()
    assert s.aliquots.set_index("aliquot_id").loc[a9, "freeze_thaw_count"] == 4
    e10 = m.loc[m.inj_type == "INJ-10", "affected_key"].item()
    assert pd.isna(s.custody_events.set_index("event_id").loc[e10, "performed_by"])


def test_clean_data_has_no_problems_and_no_repeats():
    s = generate(42, inject=False)
    assert s.injected_problems.empty
    assert s.plate_runs.repeat_of_plate_id.isna().all()
    steps = s.custody_events.groupby("sample_id").step.apply(list)
    assert (steps.map(len) == 5).all()


def test_planted_problems_are_where_the_manifest_says():
    s = generate(42)
    m = s.injected_problems
    ev = s.custody_events.set_index("event_id")
    s3 = m.loc[m.inj_type == "INJ-3", "affected_key"].item()
    assert "received" not in set(s.custody_events.loc[s.custody_events.sample_id == s3, "step"])
    e4 = m.loc[m.inj_type == "INJ-4", "affected_key"].item()
    assert (ev.loc[e4, "recorded_at"] - ev.loc[e4, "performed_at"]) > pd.Timedelta(hours=24)
    e7 = m.loc[m.inj_type == "INJ-7", "affected_key"].item()
    assert e7 in ev.index
    # INJ-2: the plate map and the LIMS disagree on exactly those two samples' wells
    swap = set(m.loc[m.inj_type == "INJ-2", "affected_key"])
    pm = s.plate_map[s.plate_map.well_type == "SAMPLE"]
    first = pm.merge(s.custody_events[s.custody_events.step == "assayed"][["plate_id", "well", "sample_id"]],
                     on=["plate_id", "well"], suffixes=("_map", "_lims"))
    diff = first[first.sample_id_map != first.sample_id_lims]
    assert set(diff.sample_id_map) == swap


def test_repeat_plates_cover_inj_1_5_6_8_samples():  # ADR 006
    s = generate(42)
    m = s.injected_problems
    rep = s.plate_runs.dropna(subset=["repeat_of_plate_id"])
    assert set(rep.repeat_of_plate_id) >= set(m.loc[m.inj_type.isin(["INJ-1", "INJ-5"]), "affected_key"])
    on_rep = s.plate_map[s.plate_map.plate_id.isin(rep.plate_id) & (s.plate_map.well_type == "SAMPLE")]
    assert set(m.loc[m.inj_type.isin(["INJ-6", "INJ-8"]), "affected_key"]) <= set(on_rep.sample_id)
    inj8 = set(m.loc[m.inj_type == "INJ-8", "affected_key"])
    assert (on_rep[on_rep.sample_id.isin(inj8)].dilution == 1000).all()
    swap = set(m.loc[m.inj_type == "INJ-2", "affected_key"])
    assert not swap & set(on_rep.sample_id)   # INJ-2 left unresolved on purpose


def _gm(x):
    return float(np.exp(np.mean(np.log(x))))


def test_clean_effect_sizes_from_true_concentrations():  # AC-1.4
    s = generate(42, inject=False)
    t = s.true_conc.merge(s.samples, on="sample_id").merge(s.subjects, on="subject_id")
    v = t[t.group_name == "Vaccine"].pivot(index="subject_id", columns="visit", values="true_conc_au_ml")
    p = t[t.group_name == "Placebo"].pivot(index="subject_id", columns="visit", values="true_conc_au_ml")
    assert _gm(v["D29"]) >= 4 * _gm(v["D1"])
    assert 0.8 <= _gm(p["D29"] / p["D1"]) <= 1.25


def test_ids_are_synthetic_patterns_only():  # AC-1.5
    s = generate(42)
    assert s.subjects.subject_id.str.fullmatch(r"SUBJ-\d{4}").all()
    assert s.samples.sample_id.str.fullmatch(r"SMP-\d{5}").all()
    assert s.aliquots.aliquot_id.str.fullmatch(r"ALQ-\d{5}-\d").all()
    assert s.custody_events.event_id.str.fullmatch(r"EVT-\d{6}").all()
    assert s.users.user_id.str.fullmatch(r"USR-\d{2}").all()
    assert s.users.display_name.map(lambda n: bool(re.fullmatch(r"(Lab Tech|Analyst|QA Reviewer) \d{2}", n))).all()
    assert not {"dob", "date_of_birth", "mrn", "name"} & {c.lower() for df in
                                                          (s.subjects, s.samples, s.users) for c in df.columns}


def test_plate_layout():
    wells = sample_wells()
    assert len(wells) == 37 and len(set(wells)) == 37
    s = generate(42)
    pm = s.plate_map[s.plate_map.plate_id == "PLATE-001"]
    assert len(pm) == 96
    assert pm.well_type.value_counts().to_dict() == {"SAMPLE": 74, "STD": 16, "BLANK": 2, "CTRL_HIGH": 2,
                                                       "CTRL_LOW": 2}
    assert s.plates["PLATE-001"].shape == (8, 12)
