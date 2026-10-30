"""DDL for the Python-written base tables (lims.*, assay.*, truth.*) and the one audited write helper (DESIGN 3.2).

Every write into lims.* and assay.* goes through `write_table`, which calls `pipeline.audit.insert_records`
(GxP seat): data rows and their audit rows land in one transaction (AC-3.1). Exceptions, by design:
`assay.ingest_errors` (holds no result) and `truth.injected_problems` (the answer key, not a GxP record).
"""

from __future__ import annotations

import pandas as pd

from pipeline.audit import init_audit, insert_records

# Who the audit trail names for writes the pipeline makes on its own (loading, parsing, fitting, QC, selection).
SYSTEM_USER = "SYS-PIPELINE"

DDL = """
create schema if not exists lims;
create schema if not exists assay;
create schema if not exists truth;

create table if not exists lims.users (
    user_id varchar primary key, display_name varchar, role varchar, active boolean);
create table if not exists lims.subjects (
    subject_id varchar primary key, group_name varchar, site_id varchar);
create table if not exists lims.samples (
    sample_id varchar primary key, subject_id varchar, visit varchar, visit_day integer, collected_at timestamp);
create table if not exists lims.aliquots (
    aliquot_id varchar primary key, sample_id varchar, created_at timestamp, freeze_thaw_count integer);
create table if not exists lims.custody_events (
    event_id varchar primary key, sample_id varchar, aliquot_id varchar, step varchar, performed_by varchar,
    performed_at timestamp, recorded_at timestamp, location varchar, plate_id varchar, well varchar, reason varchar);
create table if not exists lims.plate_runs (
    plate_id varchar primary key, run_at timestamp, analyst varchar, repeat_of_plate_id varchar);
create table if not exists lims.raw_files (
    file_name varchar primary key, plate_id varchar, raw_path varchar, sha256 varchar, ingested_at timestamp);

create table if not exists assay.plate_map (
    plate_id varchar, well varchar, well_type varchar, level integer, nominal_conc double, sample_id varchar,
    dilution integer, primary key (plate_id, well));
create table if not exists assay.well_reads (
    plate_id varchar, well varchar, row_letter varchar, col_num integer, od double, od_blank_corrected double,
    primary key (plate_id, well));
create table if not exists assay.ingest_errors (
    file_name varchar, error varchar, logged_at timestamp);
create table if not exists assay.curve_fits (
    plate_id varchar primary key, a double, b double, c double, d double, r_squared double, converged boolean,
    fit_message varchar, n_points integer, lloq_conc double, uloq_conc double, lloq_od double, uloq_od double);
create table if not exists assay.std_recovery (
    plate_id varchar, level integer, nominal_conc double, mean_od double, back_calc_conc double,
    recovery_pct double, within_limits boolean, primary key (plate_id, level));
create table if not exists assay.control_results (
    plate_id varchar, ctrl_level varchar, mean_conc double, target_conc double, low_limit double,
    high_limit double, primary key (plate_id, ctrl_level));
create table if not exists assay.sample_results (
    result_id varchar primary key, plate_id varchar, sample_id varchar, dilution integer, mean_od double,
    od_cv_pct double, range_flag varchar, conc_au_ml double, run_at timestamp);
create table if not exists assay.qc_flags (
    flag_id varchar primary key, level varchar, plate_id varchar, sample_id varchar, rule_id varchar,
    rule_version varchar, measured_value double, threshold varchar, blocking boolean, message varchar);
create table if not exists assay.plate_status (
    plate_id varchar primary key, status varchar, reject_reasons varchar, run_at timestamp);
create table if not exists assay.reportable_selection (
    sample_id varchar primary key, result_id varchar, decision varchar, reason varchar, n_runs integer);

create table if not exists truth.injected_problems (
    problem_id varchar, inj_type varchar, key_type varchar, affected_key varchar, description varchar);
"""


def create_schema(con) -> None:
    """Create the audit schema (GxP DDL) and every lims/assay/truth table. Idempotent."""
    init_audit(con)
    con.execute(DDL)


def write_table(con, table: str, df: pd.DataFrame, key_cols: list[str], reason: str,
                performed_by: str = SYSTEM_USER) -> int:
    """Audited insert (data + one audit row per record, one transaction). Returns rows inserted."""
    if df is None or df.empty:
        return 0
    df = df.astype(object).where(df.notna(), None)
    return insert_records(con, table, df, key_cols, performed_by=performed_by, reason=reason)
