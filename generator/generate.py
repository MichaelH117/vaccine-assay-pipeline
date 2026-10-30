"""Seeded synthetic vaccine-trial data: subjects, serum samples, aliquots, custody events, ELISA plates (US-1).

Everything is synthetic. IDs follow fixed patterns (SUBJ-0001, SMP-00001, USR-01) and users are "Lab Tech 01" style
labels, never real names. The same seed gives byte-identical files (fixed base date, fixed float format, "\\n" line
endings, sorted rows).

Study: 2 groups (Vaccine, Placebo) x 60 subjects, 3 visits (D1, D29, D57) = 360 serum samples. One ELISA IgG assay,
results in AU/mL (ADR 002). Samples run at 1:100.

Plate layout (96 wells, rows A-H, columns 1-12), the same on every plate:

    col 1-2   STD level k (k = 1..8, 1000 AU/mL then 3-fold down to 0.4572) in row k, duplicate in cols 1 and 2
    col 3     A3, B3 = BLANK; C3, D3 = CTRL_HIGH; E3, F3 = CTRL_LOW; G3, H3 = sample pair 1
    col 4-12  sample pairs 2..37, vertical duplicates: (A,B), (C,D), (E,F), (G,H) going down each column
    A sample pair is the first well (upper row) and the well below it. The custody `assayed` event names the first.
    Unused sample wells on a part-filled plate have no plate_map row and read at blank level.

Plates: PLATE-001..010 hold the 360 samples in order of lab receipt (37 per plate, the last one part-filled). Each
plate runs 7 days after the day its last sample was aliquoted, so receipt to assay is about 1-3 weeks.
Repeat plates (ADR 006, only when problems are injected) are pre-simulated:
    PLATE-011 repeats every sample of the INJ-5 plate, PLATE-012 every sample of the INJ-1 plate,
    PLATE-013 repeats the INJ-6 samples (1:100) and the INJ-8 samples (1:1000) from PLATE-004.

Injected problems (SPEC section 5), one manifest row per affected key in injected_problems.csv:
    INJ-1 PLATE-007: standards 2, 4 and 6 mis-pipetted at 1/5 strength (bad curve)
    INJ-2 PLATE-006: two samples swapped in the plate map vs. the LIMS `assayed` records
    INJ-3 one sample with no `received` custody event
    INJ-4 one custody event recorded 30 h after it was performed
    INJ-5 PLATE-003: high control at 1.6x its target (curve fine)
    INJ-6 3 samples on PLATE-004 whose second duplicate well reads at 45%
    INJ-7 one custody event whose audit row generator/tamper.py edits after the fact
    INJ-11 one custody event whose BASE row tamper.py re-attributes by direct SQL (audit trail untouched)
    INJ-8 3 Vaccine post-dose samples on PLATE-004 with true titers above the top standard x 100
Optional (--optional-problems): INJ-9 an aliquot with 4 freeze-thaws, INJ-10 a custody event with no performed_by.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.curve import four_pl

BASE = datetime(2026, 1, 5, 8, 0, 0)          # fixed: never now()
TS = "%Y-%m-%d %H:%M:%S"
N_PER_GROUP = 60
VISITS = (("D1", 1), ("D29", 29), ("D57", 57))
SITES = ("SITE-01", "SITE-02", "SITE-03")
STD_LEVELS = (1000, 333.3, 111.1, 37.04, 12.35, 4.115, 1.372, 0.4572)   # same as config assay.std_levels_au_ml
DILUTION = 100
CTRL_TARGET = {"CTRL_HIGH": 300.0, "CTRL_LOW": 10.0}                    # curve units, same as config controls
ROWS = "ABCDEFGH"
PER_PLATE = 37
RUN_DELAY_DAYS = 7      # a first-run plate is assayed 7 days after the day its last sample was aliquoted
REPEAT_DELAY_DAYS = 4   # a repeat plate runs 4 days after the plate it repeats

# True assay curve (blank-corrected OD vs curve-unit AU/mL) and noise. Tuned so a clean plate keeps all 8 standards
# within 80-120% recovery about 99% of the time with the unweighted fit in pipeline/curve.py.
CURVE = dict(a=0.0, b=0.7, c=150.0, d=3.5)
STD_CV, SAMPLE_CV, ADD_SD = 0.012, 0.03, 0.001
BLANK_OD = 0.05

# Fixed plate choices for the plate-level problems.
INJ1_PLATE, INJ2_PLATE, INJ5_PLATE, INJ68_PLATE = "PLATE-007", "PLATE-006", "PLATE-003", "PLATE-004"


@dataclass
class Study:
    users: pd.DataFrame
    subjects: pd.DataFrame
    samples: pd.DataFrame
    aliquots: pd.DataFrame
    custody_events: pd.DataFrame
    plate_runs: pd.DataFrame
    plate_map: pd.DataFrame
    plates: dict[str, pd.DataFrame]          # plate_id -> 8x12 OD grid (index A-H, columns 1-12)
    injected_problems: pd.DataFrame
    true_conc: pd.DataFrame = field(repr=False)   # sample_id, true_conc_au_ml (never written: the answer key is
    #                                               the manifest, not the titers)


def sample_wells() -> list[str]:
    """First well of each of the 37 sample pairs, in fill order (see module docstring)."""
    wells = ["G3"]
    for col in range(4, 13):
        wells += [f"{ROWS[r]}{col}" for r in (0, 2, 4, 6)]
    return wells


def _below(well: str) -> str:
    return f"{ROWS[ROWS.index(well[0]) + 1]}{well[1:]}"


def _fixed_wells() -> list[dict]:
    rows = []
    for k, conc in enumerate(STD_LEVELS, start=1):
        for col in (1, 2):
            rows.append(dict(well=f"{ROWS[k - 1]}{col}", well_type="STD", level=k, nominal_conc=conc))
    for well, wt in (("A3", "BLANK"), ("B3", "BLANK"), ("C3", "CTRL_HIGH"), ("D3", "CTRL_HIGH"),
                     ("E3", "CTRL_LOW"), ("F3", "CTRL_LOW")):
        rows.append(dict(well=well, well_type=wt, level=None, nominal_conc=None))
    return rows


def _ts(dt: datetime) -> str:
    return dt.strftime(TS)


def _true_titers(rng, subjects: pd.DataFrame) -> dict[tuple[str, str], float]:
    """True concentrations (AU/mL, after dilution). Baseline GMT ~250; Vaccine ~12x at D29, ~7x at D57;
    Placebo ~1x. Capped below the top standard x dilution so clean data never goes above ULOQ."""
    out = {}
    for s in subjects.itertuples():
        base = 10 ** rng.normal(np.log10(250), 0.35)
        for visit, _ in VISITS:
            if visit == "D1":
                v = base
            elif s.group_name == "Vaccine":
                v = base * 10 ** rng.normal(np.log10(12 if visit == "D29" else 7), 0.25)
            else:
                v = base * 10 ** rng.normal(0, 0.08)
            out[(s.subject_id, visit)] = float(min(v, 60000.0))
    return out


def generate(seed: int = 42, inject: bool = True, optional_problems: bool = False) -> Study:
    rng = np.random.default_rng(seed)

    users = pd.DataFrame(
        [dict(user_id=f"USR-{i:02d}", display_name=f"Lab Tech {i:02d}", role="TECH", active=True) for i in range(1, 5)]
        + [dict(user_id=f"USR-{i:02d}", display_name=f"Analyst {i - 4:02d}", role="ANALYST", active=True)
           for i in (5, 6)]
        + [dict(user_id="USR-07", display_name="QA Reviewer 01", role="QA", active=True)])
    techs, analysts = ["USR-01", "USR-02", "USR-03", "USR-04"], ["USR-05", "USR-06"]

    n = 2 * N_PER_GROUP
    groups = np.array(["Vaccine"] * N_PER_GROUP + ["Placebo"] * N_PER_GROUP)[rng.permutation(n)]
    subjects = pd.DataFrame(dict(subject_id=[f"SUBJ-{i:04d}" for i in range(1, n + 1)], group_name=groups,
                                 site_id=[SITES[i % 3] for i in range(n)]))
    titers = _true_titers(rng, subjects)

    samples, enrol = [], {}
    for i, s in enumerate(subjects.itertuples()):
        enrol[s.subject_id] = BASE + timedelta(days=int(i * 30 / n), hours=int(rng.integers(0, 8)),
                                               minutes=int(rng.integers(0, 60)))
        for visit, day in VISITS:
            samples.append(dict(sample_id=f"SMP-{len(samples) + 1:05d}", subject_id=s.subject_id, visit=visit,
                                visit_day=day, collected_at=enrol[s.subject_id] + timedelta(days=day - 1)))
    samples = pd.DataFrame(samples)
    true = pd.DataFrame(dict(sample_id=samples.sample_id,
                             true_conc_au_ml=[titers[(r.subject_id, r.visit)] for r in samples.itertuples()]))

    # ---- lab receipt and aliquoting times (drawn up front: plates are batched in order of receipt) ----
    recv_at, aliq_at_of = {}, {}
    for r in samples.itertuples():
        recv_at[r.sample_id] = r.collected_at + timedelta(hours=int(rng.integers(18, 40)),
                                                          minutes=int(rng.integers(0, 60)))
        aliq_at_of[r.sample_id] = recv_at[r.sample_id] + timedelta(hours=int(rng.integers(1, 6)),
                                                                   minutes=int(rng.integers(0, 60)))

    # ---- plate assignment: first runs, filled in order of receipt ----
    wells = sample_wells()
    sample_ids = samples.sample_id.tolist()
    first_plate = {}
    layout = []   # plate_id, sample_id, well (first of pair), dilution
    for k, sid in enumerate(sorted(sample_ids, key=lambda x: (recv_at[x], x))):
        pid = f"PLATE-{k // PER_PLATE + 1:03d}"
        first_plate[sid] = pid
        layout.append(dict(plate_id=pid, sample_id=sid, well=wells[k % PER_PLATE], dilution=DILUTION))
    n_first = len(sample_ids) // PER_PLATE + (1 if len(sample_ids) % PER_PLATE else 0)

    problems = []   # inj_type, key_type, affected_key, description

    def on_plate(pid):
        return [s for s in sample_ids if first_plate[s] == pid]

    special_plates = {INJ1_PLATE, INJ2_PLATE, INJ5_PLATE, INJ68_PLATE}
    ordinary = [s for s in sample_ids if first_plate[s] not in special_plates]
    # what is physically in each tube (INJ-8 changes it)
    true_on_plate = dict(zip(true.sample_id, true.true_conc_au_ml, strict=True))
    inj6, inj8, swap = [], [], []
    if inject:
        problems.append(("INJ-1", "plate_id", INJ1_PLATE, "standards 2, 4, 6 mis-pipetted at 1/5 strength"))
        problems.append(("INJ-5", "plate_id", INJ5_PLATE, "high control at 1.6x its target; curve fine"))
        p4 = on_plate(INJ68_PLATE)
        smp = samples.set_index("sample_id")
        grp = subjects.set_index("subject_id").group_name
        vacc_post = [s for s in p4 if smp.loc[s, "visit"] != "D1" and grp[smp.loc[s, "subject_id"]] == "Vaccine"]
        inj8 = sorted(rng.choice(vacc_post, 3, replace=False).tolist())
        for s, v in zip(inj8, (180000.0, 250000.0, 320000.0), strict=True):
            true_on_plate[s] = v
            problems.append(("INJ-8", "sample_id", s, f"true titer {v:.0f} AU/mL, above ULOQ at 1:100"))
        inj6 = sorted(rng.choice([s for s in p4 if s not in inj8], 3, replace=False).tolist())
        for s in inj6:
            problems.append(("INJ-6", "sample_id", s, "second duplicate well reads at 45% of the first"))
        swap = sorted(rng.choice(on_plate(INJ2_PLATE), 2, replace=False).tolist())
        problems.append(("INJ-2", "sample_id", swap[0], f"swapped with {swap[1]} in the plate map"))
        problems.append(("INJ-2", "sample_id", swap[1], f"swapped with {swap[0]} in the plate map"))

    # ---- plate runs (first runs, then pre-simulated repeats) ----
    runs = []
    for p in range(1, n_first + 1):
        # A plate runs one week after the day its last sample was aliquoted, so receipt-to-assay is about 1-3 weeks.
        last = max(aliq_at_of[x] for x in on_plate(f"PLATE-{p:03d}"))
        day = datetime(last.year, last.month, last.day) + timedelta(days=RUN_DELAY_DAYS)
        runs.append(dict(plate_id=f"PLATE-{p:03d}", run_at=day + timedelta(hours=9 + 4 * ((p - 1) % 2)),
                         analyst=analysts[(p - 1) % 2], repeat_of_plate_id=None))
    if inject:
        repeats = [(INJ5_PLATE, [(s, DILUTION) for s in on_plate(INJ5_PLATE)]),
                   (INJ1_PLATE, [(s, DILUTION) for s in on_plate(INJ1_PLATE)]),
                   (INJ68_PLATE, [(s, DILUTION) for s in inj6] + [(s, DILUTION * 10) for s in inj8])]
        for j, (orig, items) in enumerate(repeats):
            pid = f"PLATE-{n_first + j + 1:03d}"
            orig_at = next(x["run_at"] for x in runs if x["plate_id"] == orig)
            orig_day = datetime(orig_at.year, orig_at.month, orig_at.day)
            runs.append(dict(plate_id=pid, run_at=orig_day + timedelta(days=REPEAT_DELAY_DAYS, hours=9 + 2 * j),
                             analyst=analysts[j % 2], repeat_of_plate_id=orig))
            for k, (s, dil) in enumerate(sorted(items)):
                layout.append(dict(plate_id=pid, sample_id=s, well=wells[k], dilution=dil))
    plate_runs = pd.DataFrame(runs)
    layout = pd.DataFrame(layout)

    # ---- plate map (INJ-2: the map swaps two samples; the LIMS keeps the true positions) ----
    pm = []
    for pid in plate_runs.plate_id:
        for w in _fixed_wells():
            pm.append(dict(plate_id=pid, **w, sample_id=None, dilution=None))
        lp = layout[layout.plate_id == pid]
        mapped = dict(zip(lp.well, lp.sample_id, strict=True))
        if inject and pid == INJ2_PLATE:
            w0 = lp.loc[lp.sample_id == swap[0], "well"].item()
            w1 = lp.loc[lp.sample_id == swap[1], "well"].item()
            mapped[w0], mapped[w1] = mapped[w1], mapped[w0]
        for r in lp.itertuples():
            for w in (r.well, _below(r.well)):
                pm.append(dict(plate_id=pid, well=w, well_type="SAMPLE", level=None, nominal_conc=None,
                               sample_id=mapped[r.well], dilution=r.dilution))
    plate_map = pd.DataFrame(pm)

    # ---- raw OD grids ----
    plates = {}
    for pid in plate_runs.plate_id:
        d = CURVE["d"] * np.exp(rng.normal(0, 0.03))
        c = CURVE["c"] * np.exp(rng.normal(0, 0.05))
        bg = BLANK_OD + rng.normal(0, 0.005)
        grid = pd.DataFrame(bg + rng.normal(0, 0.002, (8, 12)), index=list(ROWS), columns=range(1, 13))

        def put(well, x, cv, scale=1.0, c=c, d=d, bg=bg, grid=grid):
            y = float(four_pl(x, CURVE["a"], CURVE["b"], c, d)) * scale
            grid.loc[well[0], int(well[1:])] = bg + y * (1 + rng.normal(0, cv)) + rng.normal(0, ADD_SD)

        for k, conc in enumerate(STD_LEVELS, start=1):
            x = conc / 5 if (inject and pid == INJ1_PLATE and k in (2, 4, 6)) else conc
            for col in (1, 2):
                put(f"{ROWS[k - 1]}{col}", x, STD_CV)
        for well in ("A3", "B3"):
            grid.loc[well[0], int(well[1:])] = bg + rng.normal(0, 0.002)
        for wt, wells_ in (("CTRL_HIGH", ("C3", "D3")), ("CTRL_LOW", ("E3", "F3"))):
            x = CTRL_TARGET[wt] * (1.6 if (inject and pid == INJ5_PLATE and wt == "CTRL_HIGH") else 1.0)
            for w in wells_:
                put(w, x, STD_CV)
        for r in layout[layout.plate_id == pid].itertuples():   # physical tube = LIMS position
            x = true_on_plate[r.sample_id] / r.dilution
            put(r.well, x, SAMPLE_CV)
            second_scale = 0.45 if (inject and r.sample_id in inj6 and pid == INJ68_PLATE) else 1.0
            put(_below(r.well), x, SAMPLE_CV, second_scale)
        plates[pid] = grid.clip(lower=0).round(3)

    # ---- aliquots and custody ----
    n_assays = layout.groupby("sample_id").size()
    analyst_of = dict(zip(plate_runs.plate_id, plate_runs.analyst, strict=True))
    site_of = dict(zip(subjects.subject_id, subjects.site_id, strict=True))
    runs_of = {s: g for s, g in layout.merge(plate_runs, on="plate_id").sort_values(["run_at", "plate_id"])
               .groupby("sample_id")}
    aliquots, events = [], []
    for r in samples.itertuples():
        received, aliq_at = recv_at[r.sample_id], aliq_at_of[r.sample_id]
        num = r.sample_id.split("-")[1]
        a1, a2 = f"ALQ-{num}-1", f"ALQ-{num}-2"
        nrun = int(n_assays.get(r.sample_id, 0))
        aliquots.append(dict(aliquot_id=a1, sample_id=r.sample_id, created_at=aliq_at, freeze_thaw_count=nrun))
        aliquots.append(dict(aliquot_id=a2, sample_id=r.sample_id, created_at=aliq_at, freeze_thaw_count=0))
        tech = techs[int(rng.integers(0, 4))]
        site = site_of[r.subject_id]
        evs = [("collected", None, r.collected_at, site, None, None, None),
               ("received", None, received, "RECEIVING", None, None, None),
               ("aliquoted", a1, aliq_at, "BENCH-01", None, None, None)]
        sl = runs_of.get(r.sample_id, layout.iloc[0:0].merge(plate_runs, on="plate_id"))
        for j, x in enumerate(sl.itertuples()):
            evs.append(("assayed", a1, x.run_at, "ELISA-LAB", x.plate_id, x.well,
                        None if j == 0 else f"repeat run on {x.plate_id} (repeat of {x.repeat_of_plate_id})"))
            if j == 0:
                evs.append(("stored", a1, x.run_at + timedelta(hours=3), "FRZ-80-01", None, None, None))
        for step, alq, at, loc, pid, well, reason in evs:
            by = analyst_of[pid] if step == "assayed" else tech
            events.append(dict(sample_id=r.sample_id, aliquot_id=alq, step=step, performed_by=by, performed_at=at,
                               recorded_at=at + timedelta(minutes=int(rng.integers(1, 120))), location=loc,
                               plate_id=pid, well=well, reason=reason))
    custody = pd.DataFrame(events)
    custody.insert(0, "event_id", [f"EVT-{i:06d}" for i in range(1, len(custody) + 1)])
    aliquots = pd.DataFrame(aliquots)

    if inject:
        pool = sorted(set(ordinary) - set(inj6) - set(inj8) - set(swap))
        s3, s4, s7, s9, s10, s11 = rng.choice(pool, 6, replace=False).tolist()
        drop = custody[(custody.sample_id == s3) & (custody.step == "received")].event_id.item()
        custody = custody[custody.event_id != drop].reset_index(drop=True)
        problems.append(("INJ-3", "sample_id", s3, f"`received` custody event missing ({drop} never recorded)"))
        e4 = custody[(custody.sample_id == s4) & (custody.step == "aliquoted")].event_id.item()
        custody.loc[custody.event_id == e4, "recorded_at"] = (
            custody.loc[custody.event_id == e4, "performed_at"] + timedelta(hours=30))
        problems.append(("INJ-4", "event_id", e4, "custody event recorded 30 h after it was performed"))
        e7 = custody[(custody.sample_id == s7) & (custody.step == "stored")].event_id.item()
        problems.append(("INJ-7", "event_id", e7, "audit_log row for this event edited by direct SQL (tamper.py)"))
        e11 = custody[(custody.sample_id == s11) & (custody.step == "collected")].event_id.item()
        problems.append(("INJ-11", "event_id", e11,
                         "custody row re-attributed by direct SQL UPDATE, audit trail untouched (tamper_base_row)"))
        if optional_problems:
            a9 = f"ALQ-{s9.split('-')[1]}-1"
            aliquots.loc[aliquots.aliquot_id == a9, "freeze_thaw_count"] = 4
            problems.append(("INJ-9", "aliquot_id", a9, "aliquot freeze-thawed 4 times"))
            e10 = custody[(custody.sample_id == s10) & (custody.step == "received")].event_id.item()
            custody.loc[custody.event_id == e10, "performed_by"] = None
            problems.append(("INJ-10", "event_id", e10, "custody event with no performed_by"))

    order = {f"INJ-{i}": i for i in range(1, 12)}
    problems.sort(key=lambda p: (order[p[0]], p[2]))
    manifest = pd.DataFrame(problems, columns=["inj_type", "key_type", "affected_key", "description"])
    # One problem_id per problem; the INJ-2 swap is one problem with two keys.
    pid_of, ids = {}, []
    for p in manifest.itertuples():
        key = p.inj_type if p.inj_type == "INJ-2" else (p.inj_type, p.affected_key)
        pid_of.setdefault(key, f"P-{len(pid_of) + 1:03d}")
        ids.append(pid_of[key])
    manifest.insert(0, "problem_id", ids)

    return Study(users=users, subjects=subjects, samples=samples, aliquots=aliquots,
                 custody_events=custody.sort_values("event_id").reset_index(drop=True), plate_runs=plate_runs,
                 plate_map=plate_map.sort_values(["plate_id", "well"]).reset_index(drop=True), plates=plates,
                 injected_problems=manifest, true_conc=true)


def _to_csv(df: pd.DataFrame, path: Path) -> None:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]) or out[col].map(type).eq(datetime).any():
            out[col] = out[col].map(lambda v: _ts(v) if isinstance(v, datetime) else v)
    out.to_csv(path, index=False, lineterminator="\n")


def write(study: Study, landing: Path) -> dict[str, int]:
    """Write every table as CSV plus plates/PLATE-NNN.csv. Returns row counts per file."""
    landing = Path(landing)
    (landing / "plates").mkdir(parents=True, exist_ok=True)
    for old in (landing / "plates").glob("*.csv"):
        old.unlink()
    counts = {}
    for name in ("users", "subjects", "samples", "aliquots", "custody_events", "plate_runs", "plate_map",
                 "injected_problems"):
        df = getattr(study, name)
        _to_csv(df, landing / f"{name}.csv")
        counts[name] = len(df)
    for pid, grid in study.plates.items():
        lines = [",".join([""] + [str(c) for c in grid.columns])]
        lines += [",".join([r] + [f"{v:.3f}" for v in grid.loc[r]]) for r in grid.index]
        (landing / "plates" / f"{pid}.csv").write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    counts["plates"] = len(study.plates)
    return counts


def file_hashes(landing: Path) -> dict[str, str]:
    """SHA-256 of every generated file (relative path -> hex digest), for the reproducibility test (AC-1.1)."""
    landing = Path(landing)
    return {p.relative_to(landing).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(landing.rglob("*.csv"))}


if __name__ == "__main__":
    import argparse

    from pipeline.config import default_paths

    ap = argparse.ArgumentParser(description="Write the synthetic study to data/landing/")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clean", action="store_true", help="no injected problems")
    ap.add_argument("--optional-problems", action="store_true")
    a = ap.parse_args()
    print(write(generate(a.seed, not a.clean, a.optional_problems), default_paths().landing))
