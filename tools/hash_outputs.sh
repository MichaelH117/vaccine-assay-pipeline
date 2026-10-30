#!/bin/sh
# Repeat-run check, part 1 (FLAW_HUNT FH-01). Usage: sh tools/hash_outputs.sh OUTFILE
# SHA-256 of every generated output of one `python -m pipeline.run`: landing CSVs, read-only raw copies, mart
# exports (CSV + Parquet), the DuckDB file, the audit anchor, docs/results.json and the chart PNGs.
# Run the pipeline, hash to run1.sha256, run it again, hash to run2.sha256, then `diff` the two files.
cd "$(dirname "$0")/.." || exit 1
find data/landing data/raw data/marts data/warehouse -type f ! -path '*dbt_logs*' ! -path '*dbt_target*' | sort | xargs sha256sum > "$1"
sha256sum docs/results.json docs/img/gmt_by_group_visit.png docs/img/plate_4pl_curve.png docs/img/plate_status_grid.png >> "$1"
wc -l < "$1"
