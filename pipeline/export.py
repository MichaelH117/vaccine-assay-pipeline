"""Export marts and DESIGN section 8 tables to data/marts/ as CSV + Parquet for Power BI (owner: LIA, AC-11.3).

DuckDB writes both formats itself (COPY), so no pyarrow is needed. Rows are sorted on the first column so the files
are stable between runs with the same seed.
"""

from __future__ import annotations

from pathlib import Path

# (qualified source table, export file stem). The stem is what docs/DASHBOARD_SPEC.md names.
EXPORT_TABLES: list[tuple[str, str]] = [
    ("marts.mart_immunogenicity", "mart_immunogenicity"),
    ("marts.mart_lab_kpis", "mart_lab_kpis"),
    ("marts.mart_plate_qc", "mart_plate_qc"),
    ("marts.detection_scorecard", "detection_scorecard"),
    ("marts.scorecard_false_positives", "scorecard_false_positives"),
    ("marts.scorecard_summary", "scorecard_summary"),
    ("core.fct_reportable_result", "fct_reportable_result"),
    ("integrity.alcoa_findings", "alcoa_findings"),
    ("integrity.v_custody_status", "v_custody_status"),
    ("assay.control_results", "control_results"),
]


def _sql_path(p: Path) -> str:
    return p.resolve().as_posix().replace("'", "''")


def export_marts(con, out: Path) -> dict[str, int]:
    """Write every EXPORT_TABLES entry to out/<stem>.csv and out/<stem>.parquet. Returns rows per stem.

    Raises if a source table is missing: an incomplete Power BI import must not pass silently.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for table, stem in EXPORT_TABLES:
        first_col = con.execute(f"select * from {table} limit 0").description[0][0]
        query = f'select * from {table} order by "{first_col}"'
        con.execute(f"copy ({query}) to '{_sql_path(out / f'{stem}.csv')}' (header, delimiter ',')")
        con.execute(f"copy ({query}) to '{_sql_path(out / f'{stem}.parquet')}' (format parquet)")
        counts[stem] = int(con.execute(f"select count(*) from {table}").fetchone()[0])
    return counts
