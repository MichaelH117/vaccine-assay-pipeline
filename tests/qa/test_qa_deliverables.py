"""QA checks for deliverables that had no automated test: KPI definitions in METRICS.md (AC-9.2), the dashboard
spec structure (AC-11.1, 11.2), the Power BI exports (AC-11.3) and the 3 PNG charts (AC-11.4). Uses the shared
`built` fixture; output goes to tmp folders, never the repo."""

from __future__ import annotations

import re

import duckdb
import pandas as pd

from pipeline.charts import render_charts
from pipeline.config import ROOT
from pipeline.export import export_marts

METRICS = (ROOT / "docs" / "METRICS.md").read_text(encoding="utf-8")
DASH = (ROOT / "docs" / "DASHBOARD_SPEC.md").read_text(encoding="utf-8")


def test_every_kpi_id_is_defined_in_metrics_md(built):
    ids = [r[0] for r in built["con"].execute("select kpi_id from marts.mart_lab_kpis").fetchall()]
    assert len(ids) >= 9
    undefined = [k for k in ids if f"`{k}`" not in METRICS and not k.startswith("PLATE_REJECT_")]
    assert undefined == [], f"KPIs with no METRICS.md definition: {undefined}"
    assert "PLATE_REJECT_<RULE>" in METRICS


def test_spec_kpis_all_present(built):
    ids = {r[0] for r in built["con"].execute("select kpi_id from marts.mart_lab_kpis").fetchall()}
    for need in ("TAT_MEDIAN_DAYS", "TAT_P90_DAYS", "PLATE_FAIL_RATE", "REASSAY_RATE", "CUSTODY_COMPLETE_PCT",
                 "ALCOA_FINDINGS_PER_100"):
        assert need in ids


def test_dashboard_spec_has_three_pages_and_named_visuals():
    for page in ("Immunogenicity", "Assay QC", "Lab ops and data integrity"):
        assert re.search(rf"^## Page \d: {re.escape(page)}", DASH, re.M), page
    for visual in ("Reverse cumulative", "Seroresponse table", "Plate status grid", "Curve fit gallery",
                   "Levey-Jennings", "KPI cards", "Custody funnel", "ALCOA+ findings table"):
        assert visual.lower() in DASH.lower(), visual
    assert "data/marts/" in DASH and "DAX" in DASH


def test_exports_write_csv_and_parquet_that_tie_out(built, tmp_path):
    counts = export_marts(built["con"], tmp_path)
    assert counts, "nothing exported"
    for stem, n in counts.items():
        csv, pq = tmp_path / f"{stem}.csv", tmp_path / f"{stem}.parquet"
        assert csv.exists() and pq.exists(), stem
        n_pq = duckdb.connect().execute("select count(*) from read_parquet(?)", [str(pq)]).fetchone()[0]
        assert len(pd.read_csv(csv)) == n == n_pq, stem
    for need in ("mart_immunogenicity", "mart_lab_kpis", "mart_plate_qc", "detection_scorecard"):
        assert need in counts


def test_three_png_charts_rendered(built, tmp_path):
    pngs = render_charts(built["con"], tmp_path)
    assert len(pngs) >= 3
    for p in pngs:
        data = open(p, "rb").read()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 10_000, p
