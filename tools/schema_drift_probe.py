"""Schema-drift probe (FLAW_HUNT FH-03). Run from the repo root: PYTHONPATH=. python tools/schema_drift_probe.py

Copies data/landing to a temp folder, changes one landing CSV header per case (extra, dropped, renamed column), and
loads it with load_lims into a fresh DuckDB. Prints REJECTED or ACCEPTED SILENTLY per case. Needs a built data/.
"""
import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.lims_load import load_lims
from pipeline.schema import create_schema

CASES = {
    "extra column on samples.csv": ("samples.csv", lambda df: df.assign(new_col="x")),
    "dropped column subjects.site_id": ("subjects.csv", lambda df: df.drop(columns=["site_id"])),
    "renamed custody performed_by->operator": ("custody_events.csv",
                                               lambda df: df.rename(columns={"performed_by": "operator"})),
}


def main() -> None:
    src = Path("data/landing")
    for name, (file_name, change) in CASES.items():
        work = Path(tempfile.mkdtemp())
        shutil.copytree(src, work / "landing")
        path = work / "landing" / file_name
        change(pd.read_csv(path, dtype=str, keep_default_na=False)).to_csv(path, index=False)
        con = duckdb.connect(str(work / "probe.duckdb"))
        create_schema(con)
        try:
            load_lims(con, work / "landing")
            print(f"{name}: ACCEPTED SILENTLY")
        except Exception as e:  # noqa: BLE001 - the probe reports whatever the loader raises
            print(f"{name}: REJECTED -> {type(e).__name__}: {str(e).splitlines()[0][:160]}")
        finally:
            con.close()


if __name__ == "__main__":
    main()
