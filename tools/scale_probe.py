"""Scale probe (SCALE_AND_COST.md). Run from the repo root: PYTHONPATH=. python -u tools/scale_probe.py FACTOR OUT_DIR

Rebuilds a CLEAN synthetic study (no planted problems: the planting logic assumes the 1x plate layout) with
N_PER_GROUP x FACTOR subjects into OUT_DIR/data, and prints one JSON line with sizes and the elapsed time at which
each pipeline step started. Not part of the product; never writes to the repo's data/.
"""
import builtins
import json
import sys
import time
from pathlib import Path

import duckdb

import generator.generate as gen
import pipeline.run as run


def main(factor: int, out: Path) -> None:
    gen.N_PER_GROUP = 60 * factor
    marks = []
    t0 = time.perf_counter()
    real_print = builtins.print

    def stamp(*args, **kwargs):
        marks.append((round(time.perf_counter() - t0, 1), " ".join(map(str, args))[:60]))
        real_print(*args, **kwargs)

    builtins.print = stamp
    try:
        paths = run.build(out, seed=42, inject=False)
    finally:
        builtins.print = real_print
    total = time.perf_counter() - t0
    con = duckdb.connect(str(paths.db), read_only=True)

    def q(sql: str):
        return con.execute(sql).fetchone()[0]

    res = {"factor": factor, "samples": q("select count(*) from lims.samples"),
           "plates": q("select count(*) from lims.plate_runs"),
           "well_reads": q("select count(*) from assay.well_reads"),
           "audit_rows": q("select count(*) from audit.audit_log"), "db_mb": round(paths.db.stat().st_size / 1e6, 1),
           "total_s": round(total, 1), "dbt": run.LAST_DBT,
           "headline": q("select headline from marts.scorecard_summary"),
           "step_marks_s": marks}
    print(json.dumps(res))


if __name__ == "__main__":
    main(int(sys.argv[1]), Path(sys.argv[2]))
