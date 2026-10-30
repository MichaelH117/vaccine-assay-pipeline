"""Load the landing CSVs into the mini-LIMS tables (lims.*), every row through the audit API (US-2, AC-3.1)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline.schema import write_table

# table -> (key columns, timestamp columns, integer columns, boolean columns)
LIMS_TABLES: dict[str, tuple[list[str], list[str], list[str], list[str]]] = {
    "users": (["user_id"], [], [], ["active"]),
    "subjects": (["subject_id"], [], [], []),
    "samples": (["sample_id"], ["collected_at"], ["visit_day"], []),
    "aliquots": (["aliquot_id"], ["created_at"], ["freeze_thaw_count"], []),
    "custody_events": (["event_id"], ["performed_at", "recorded_at"], [], []),
    "plate_runs": (["plate_id"], ["run_at"], [], []),
}


class LandingSchemaError(ValueError):
    """A landing CSV header does not match the table contract (DESIGN section 3.1)."""


def table_columns(con, table: str) -> list[str]:
    schema, name = table.split(".")
    return [c for (c,) in con.execute("select column_name from information_schema.columns where table_schema = ? "
                                      "and table_name = ? order by ordinal_position", [schema, name]).fetchall()]


def read_landing(path: Path, ts_cols=(), int_cols=(), bool_cols=(), expected: list[str] | None = None) -> pd.DataFrame:
    """Read a landing CSV as text, then type the named columns. Empty cells become null.
    With `expected`, the header must contain exactly those columns: a missing column would otherwise load as all
    nulls without any error (BUG-011), and an extra one is an unannounced contract change."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    if expected is not None:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        if missing or extra:
            raise LandingSchemaError(f"{Path(path).name}: header does not match the contract; "
                                     f"missing {missing}, unexpected {extra}")
    for c in ts_cols:
        df[c] = pd.to_datetime(df[c], format="%Y-%m-%d %H:%M:%S")
    for c in int_cols:
        df[c] = pd.to_numeric(df[c]).astype("Int64")
    for c in bool_cols:
        df[c] = df[c].str.lower().map({"true": True, "false": False})
    return df


def load_lims(con, landing: Path) -> dict[str, int]:
    """Insert users, subjects, samples, aliquots, custody_events and plate_runs. Returns rows per table."""
    counts = {}
    for name, (keys, ts, ints, bools) in LIMS_TABLES.items():
        df = read_landing(Path(landing) / f"{name}.csv", ts, ints, bools,
                          expected=table_columns(con, f"lims.{name}"))
        counts[name] = write_table(con, f"lims.{name}", df, keys, f"LIMS load from landing/{name}.csv")
    return counts
