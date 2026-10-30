"""Test helper (GxP seat): run the dbt integrity models' SQL on hand-made staging fixtures, without dbt.

The models are rendered with Jinja using a minimal ``ref``/``var`` shim. Vars come from the real config through
``pipeline.config.dbt_vars``, so the tests use the same thresholds as the pipeline. This lets GXP-04/05 logic be
tested before DE-08 staging exists; the full-build tests in test_custody.py / test_alcoa.py cover the real dbt run.

Fixture story (one row = one custody event; steps collected, received, aliquoted, assayed, stored):
  SMP-00001  complete chain + a repeat `assayed` after `stored` (must NOT be CUSTODY_ORDER, DESIGN R8);
             EVT-000006 recorded exactly 24h after performed (boundary: not late)
  SMP-00002  `received` missing -> CUSTODY_GAP; EVT-000007 recorded 24h + 1s late -> LATE_ENTRY
  SMP-00003  `received` performed before `collected` -> CUSTODY_ORDER; EVT-000011 no performer -> NO_PERFORMER;
             EVT-000012 by USR-99 (not a user) -> UNKNOWN_USER
  SMP-00004  in progress (collected, received only): incomplete, but no flag
  SMP-00005  no events at all: incomplete, no flag
  ALQ-00003-1 freeze_thaw_count 3 > 2 -> FREEZE_THAW_EXCEEDED; ALQ-00001-1 has exactly 2 (boundary: no flag)
  EVT-000004 base row edited after audit (latest reconciliation run) -> RECORD_MISMATCH; EVT-000002 was only in an
             older run -> none
  PLATE-002 latest re-hash mismatches -> HASH_MISMATCH; PLATE-003 mismatched earlier but latest check matches -> none
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import jinja2

from pipeline.config import dbt_vars, load_rules

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "dbt" / "models" / "integrity"

_T0 = "2026-01-05 09:00:00"


def _ev(eid, sample, step, by, performed, recorded=None, aliquot=None):
    return (f"EVT-{eid:06d}", sample, aliquot, step, by, performed, recorded or performed)


EVENTS = [
    _ev(1, "SMP-00001", "collected", "USR-01", "2026-01-05 09:00:00"),
    _ev(2, "SMP-00001", "received", "USR-02", "2026-01-06 09:00:00"),
    _ev(3, "SMP-00001", "aliquoted", "USR-02", "2026-01-06 10:00:00", aliquot="ALQ-00001-1"),
    _ev(4, "SMP-00001", "assayed", "USR-03", "2026-01-08 10:00:00", aliquot="ALQ-00001-1"),
    _ev(5, "SMP-00001", "stored", "USR-02", "2026-01-08 16:00:00", aliquot="ALQ-00001-1"),
    _ev(6, "SMP-00001", "assayed", "USR-03", "2026-01-12 10:00:00", "2026-01-13 10:00:00", "ALQ-00001-1"),
    _ev(7, "SMP-00002", "collected", "USR-01", "2026-01-05 09:00:00", "2026-01-06 09:00:01"),
    _ev(8, "SMP-00002", "aliquoted", "USR-02", "2026-01-06 10:00:00", aliquot="ALQ-00002-1"),
    _ev(9, "SMP-00002", "assayed", "USR-03", "2026-01-08 10:00:00", aliquot="ALQ-00002-1"),
    _ev(10, "SMP-00002", "stored", "USR-02", "2026-01-08 16:00:00", aliquot="ALQ-00002-1"),
    _ev(11, "SMP-00003", "collected", None, "2026-01-05 09:00:00"),
    _ev(12, "SMP-00003", "received", "USR-99", "2026-01-04 09:00:00"),
    _ev(13, "SMP-00003", "aliquoted", "USR-02", "2026-01-06 10:00:00", aliquot="ALQ-00003-1"),
    _ev(14, "SMP-00003", "assayed", "USR-03", "2026-01-08 10:00:00", aliquot="ALQ-00003-1"),
    _ev(15, "SMP-00003", "stored", "USR-02", "2026-01-08 16:00:00", aliquot="ALQ-00003-1"),
    _ev(16, "SMP-00004", "collected", "USR-01", "2026-01-05 09:00:00"),
    _ev(17, "SMP-00004", "received", "USR-02", "2026-01-06 09:00:00"),
]


def load_fixture(events=None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA staging; CREATE SCHEMA integrity")
    con.execute("CREATE TABLE staging.stg_users (user_id VARCHAR, display_name VARCHAR, role VARCHAR, active BOOLEAN)")
    con.execute("INSERT INTO staging.stg_users VALUES ('USR-01','Lab Tech 01','TECH',true),"
                "('USR-02','Lab Tech 02','TECH',true),('USR-03','Analyst 03','ANALYST',true)")
    con.execute("CREATE TABLE staging.stg_samples (sample_id VARCHAR, subject_id VARCHAR, visit VARCHAR)")
    con.execute("INSERT INTO staging.stg_samples SELECT 'SMP-0000' || i, 'SUBJ-000' || i, 'D1' FROM range(1, 6) t(i)")
    con.execute("CREATE TABLE staging.stg_aliquots (aliquot_id VARCHAR, sample_id VARCHAR, created_at TIMESTAMP, "
                "freeze_thaw_count INTEGER)")
    con.execute(f"INSERT INTO staging.stg_aliquots VALUES ('ALQ-00001-1','SMP-00001','{_T0}',2),"
                f"('ALQ-00002-1','SMP-00002','{_T0}',1),('ALQ-00003-1','SMP-00003','{_T0}',3)")
    con.execute("CREATE TABLE staging.stg_custody_events (event_id VARCHAR, sample_id VARCHAR, aliquot_id VARCHAR, "
                "step VARCHAR, performed_by VARCHAR, performed_at TIMESTAMP, recorded_at TIMESTAMP, location VARCHAR, "
                "plate_id VARCHAR, well VARCHAR, reason VARCHAR)")
    con.executemany("INSERT INTO staging.stg_custody_events VALUES (?, ?, ?, ?, ?, ?, ?, 'SITE-01', NULL, NULL, NULL)",
                    [list(e) for e in (EVENTS if events is None else events)])
    con.execute("CREATE TABLE staging.stg_file_integrity (file_name VARCHAR, plate_id VARCHAR, stored_sha256 VARCHAR, "
                "current_sha256 VARCHAR, matches BOOLEAN, checked_at TIMESTAMP)")
    con.execute("INSERT INTO staging.stg_file_integrity VALUES "
                "('PLATE-001.csv','PLATE-001','aa','aa',true,'2026-01-09 00:00:00'),"
                "('PLATE-002.csv','PLATE-002','bb','cc',false,'2026-01-09 00:00:00'),"
                "('PLATE-003.csv','PLATE-003','dd','ee',false,'2026-01-08 00:00:00'),"
                "('PLATE-003.csv','PLATE-003','dd','dd',true,'2026-01-09 00:00:00')")
    con.execute("CREATE SCHEMA gxp_audit")
    con.execute("CREATE TABLE gxp_audit.record_reconciliation (checked_at TIMESTAMP, table_name VARCHAR, "
                "key_type VARCHAR, record_key VARCHAR, issue VARCHAR, audit_seq BIGINT, detail VARCHAR)")
    con.execute("INSERT INTO gxp_audit.record_reconciliation VALUES "
                "('2026-01-08 00:00:00', 'lims.custody_events', 'event_id', 'EVT-000002', 'RECORD_MODIFIED', 2, 'old'),"
                "('2026-01-08 00:00:00', NULL, NULL, NULL, 'RUN', NULL, '1 issue(s)'),"
                "('2026-01-09 00:00:00', NULL, NULL, NULL, 'RUN', NULL, '1 issue(s)'),"
                "('2026-01-09 00:00:00', 'lims.custody_events', 'event_id', 'EVT-000004', 'RECORD_MODIFIED', 4, "
                "'performed_by: \"USR-03\" -> \"USR-01\"')")
    return con


def render(model: str, deps: tuple[str, ...] = ()) -> str:
    vars_ = dbt_vars(load_rules())

    def ref(name):
        return f"integrity.{name}" if name in deps or (MODELS / f"{name}.sql").exists() else f"staging.{name}"

    def source(schema, table):
        return f"{schema}.{table}"

    def var(name, default=None):
        return vars_.get(name, default)

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string((MODELS / f"{model}.sql").read_text(encoding="utf-8"))
    return template.render(ref=ref, var=var, source=source)


def render_and_run(con, model: str, deps=()) -> list[dict]:
    """Build each dependency model then ``model`` as tables in schema integrity; return model rows as dicts."""
    for name in [*deps, model]:
        con.execute(f"CREATE OR REPLACE TABLE integrity.{name} AS {render(name, tuple(deps))}")
    cur = con.execute(f"SELECT * FROM integrity.{model}")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
