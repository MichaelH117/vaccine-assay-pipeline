"""QA helpers (owner: QA seat). Black-box builds with a hook that edits the landing data before the pipeline reads it.

`staged_build` repeats the step order of pipeline.run.build() (DESIGN section 1) so a test can plant its own problem
between "generate" and "load". It never touches the repo's data/ folder: callers pass a pytest tmp folder.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd

from generator.generate import generate, write
from pipeline.config import Paths, dbt_vars, default_paths, load_rules
from pipeline.curve import fit_all
from pipeline.ingest import ingest_plates
from pipeline.lims_load import load_lims
from pipeline.qc import run_qc
from pipeline.reportable import select_reportable
from pipeline.run import integrity_step, load_truth, run_dbt
from pipeline.schema import create_schema


def staged_build(root: Path, mutate: Callable[[Path], dict] | None = None, seed: int = 42,
                 with_dbt: bool = True) -> tuple[Paths, dict, dict | None]:
    """generate -> mutate(landing) -> the Python pipeline steps -> (optionally) dbt build.
    Returns (paths, whatever mutate returned, dbt counts or None). Exceptions from the pipeline propagate."""
    rules = load_rules()
    paths = default_paths(root)
    write(generate(seed, inject=True), paths.landing)
    info = mutate(paths.landing) if mutate else {}
    paths.db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(paths.db))
    try:
        create_schema(con)
        load_lims(con, paths.landing)
        ingest_plates(con, paths.landing, paths.raw, rules)
        fit_all(con, rules)
        run_qc(con, rules)
        select_reportable(con)
        load_truth(con, paths.landing)
        truth = con.execute("select * from truth.injected_problems").df()
        integrity_step(con, paths, truth)   # same step 7 as pipeline.run.build (tamper INJ-7/11, verify, anchor)
    finally:
        con.close()
    counts = run_dbt(paths.db, dbt_vars(rules)) if with_dbt else None
    return paths, info, counts


def clean_plates(landing: Path) -> list[str]:
    """First-run plates with no injected problem on them and no repeat run, so a QA mutation cannot hide or fake a
    planted problem."""
    pm = pd.read_csv(landing / "plate_map.csv", dtype=str)
    truth = pd.read_csv(landing / "injected_problems.csv", dtype=str)
    runs = pd.read_csv(landing / "plate_runs.csv", dtype=str)
    bad_samples = set(truth.loc[truth.key_type == "sample_id", "affected_key"])
    bad = set(truth.loc[truth.key_type == "plate_id", "affected_key"])
    bad |= set(runs.repeat_of_plate_id.dropna()) | set(runs.loc[runs.repeat_of_plate_id.notna(), "plate_id"])
    bad |= set(pm.loc[pm.sample_id.isin(bad_samples), "plate_id"])
    return sorted(set(pm.plate_id) - bad)


def plate_samples(landing: Path, plate_id: str) -> list[str]:
    pm = pd.read_csv(landing / "plate_map.csv", dtype=str)
    return sorted(pm.loc[(pm.plate_id == plate_id) & (pm.well_type == "SAMPLE"), "sample_id"].unique())


def read_plate(landing: Path, plate_id: str) -> pd.DataFrame:
    return pd.read_csv(landing / "plates" / f"{plate_id}.csv", index_col=0, dtype=str)


def write_plate(landing: Path, plate_id: str, df: pd.DataFrame) -> None:
    df.to_csv(landing / "plates" / f"{plate_id}.csv")
