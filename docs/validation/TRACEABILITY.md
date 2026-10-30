# Traceability Matrix (demo): DRAFT

Owner: GxP Validation Engineer seat. Version 0.2 **DRAFT**, 2026-10-30. Final version in Phase 2 (GXP-07), filled with
the real pytest and `dbt test` output after QA-02.

> Demonstration on synthetic data. Not a validated system; no regulatory compliance is claimed.

Result column: **PASS (unit)** = passed in the GxP seat's own run on 2026-10-29 (`.venv\Scripts\python -m pytest
tests/test_audit.py tests/test_custody.py tests/test_alcoa.py tests/qa/test_qa_audit_chain.py`: 70 passed on
2026-10-30, now including the full-build tests because the `built` fixtures exist). **PENDING** = test written
but needs the full build (`built` / `clean_built` fixtures, DE-09) or belongs to another seat. Nothing here is
final until GXP-07.

| URS | Risk | Design | Test(s) | Result |
|---|---|---|---|---|
| URS-01 who/what/when/why on insert | H | DESIGN 3.2 audit_log; `pipeline/audit.py::insert_records` | `test_audit.py::test_insert_writes_data_and_one_audit_row_per_record`; `::test_every_base_table_row_has_an_insert_audit_row` | PASS (unit); build PENDING |
| URS-02 no update/delete | H | ADR 001; `audit.update`, `audit.delete` | `test_audit.py::test_update_and_delete_always_raise` | PASS (unit) |
| URS-03 corrections append and point back | H | `audit.correct_record` | `test_audit.py::test_correction_appends_row_pointing_to_superseded_row`, `::test_correction_validation` | PASS (unit) |
| URS-04 no silent overwrite | H | `insert_records` key check | `test_audit.py::test_reinsert_same_key_is_refused_no_silent_overwrite`, `::test_duplicate_keys_within_batch_refused` | PASS (unit) |
| URS-05 one transaction | H | `insert_records` begin/commit/rollback | `test_audit.py::test_failed_batch_rolls_back_data_and_audit`, `::test_audit_failure_rolls_back_the_data_insert` | PASS (unit) |
| URS-06 who and why required | H | `_require_text` | `test_audit.py::test_who_and_why_are_required` | PASS (unit) |
| URS-07 hash chain + verify | H | DESIGN 3.2 hash rule; `verify_chain`; `generator/tamper.py`; `integrity.write_chain_verify` | `test_audit.py::test_clean_chain_verifies`, `::test_direct_sql_update_breaks_chain_at_that_row`, `::test_deleted_row_breaks_chain`, `::test_rehashed_forgery_still_breaks_at_next_row`, `::test_tamper_then_verify_names_the_tampered_event`, `::test_chain_broken_exactly_at_inj7_on_build`, `::test_chain_ok_on_clean_build` | PASS (unit); build PENDING |
| URS-29 base rows reconcile with audit trail | H | `audit.reconcile`, RECORD check in `verify_chain`, `integrity.reconcile_records`, `alcoa_findings` ALCOA-O2, `generator/tamper.py::tamper_base_row` (INJ-11) | `test_audit.py::test_clean_load_reconciles`, `::test_audit_payload_is_the_stored_row`, `::test_base_row_edit_is_found_with_field_diff`, `::test_base_row_delete_and_direct_insert_are_found`, `::test_correction_does_not_count_as_mismatch`, `::test_reconcile_records_writes_run_marker_and_issues`, `::test_tamper_base_row_reassigns_performer_and_is_caught`; `test_alcoa.py::test_alcoa_findings_on_fixture`; QA `test_qa_audit_chain.py::test_base_table_edit_detected` | PASS; INJ-11 scorecard PENDING (DE generator + run.py, LIA scorecard) |
| URS-30 tail truncation / tail re-hash | H | `audit.chain_checkpoint`, CHECKPOINT and ANCHOR checks, `integrity.write_chain_anchor` | `test_audit.py::test_every_write_appends_a_checkpoint`, `::test_tail_truncation_caught_by_checkpoint`, `::test_rows_appended_outside_api_caught`, `::test_forger_who_rewrites_checkpoints_is_caught_only_by_external_anchor`, `::test_anchor_file_is_write_once_and_read_only`; QA `::test_last_row_deleted_detected`, `::test_last_row_edit_with_rehash_detected` | PASS; anchor in run.py PENDING (DE) |
| URS-08 read-only raw copies | H | DE `ingest.py` (AC-3.5) | `test_alcoa.py::test_raw_files_are_read_only`; DE `test_ingest.py` | PASS (unit); DE PENDING |
| URS-09 re-hash raw files | H | `integrity.rehash_raw_files`; `alcoa_findings` ALCOA-O1 | `test_alcoa.py::test_rehash_clean_files_all_match`, `::test_edited_raw_file_gives_mismatch`, `::test_raw_files_match_on_build` | PASS (unit); build PENDING |
| URS-10 ALCOA+ findings | M | `dbt/models/integrity/alcoa_findings.sql` | `test_alcoa.py::test_alcoa_findings_on_fixture`, `::test_late_entry_boundary_is_strictly_greater_than_limit`, `::test_inj4_late_entry_detected_on_build`; dbt tests in `_integrity.yml` | PASS (fixture); build + dbt PENDING |
| URS-11 LIMS tables | M | DE `schema.py`, `lims_load.py` | DE tests | PENDING (DE) |
| URS-12 custody status | M | `v_custody_status.sql` | `test_custody.py::test_custody_status_on_fixture`, `::test_clean_data_has_no_custody_flags` | PASS (fixture); build PENDING |
| URS-13 CUSTODY_GAP | M | `custody_flags.sql` | `test_custody.py::test_custody_flags_on_fixture`, `::test_multiple_missing_steps_listed_in_order`, `::test_inj3_flagged_with_received_missing` | PASS (fixture); build PENDING |
| URS-14 CUSTODY_ORDER | M | `custody_flags.sql` (first occurrence) | `test_custody.py::test_custody_flags_on_fixture`, `::test_repeat_assay_after_stored_is_not_out_of_order` | PASS (fixture) |
| URS-15 FREEZE_THAW_EXCEEDED | M | `custody_flags.sql` | `test_custody.py::test_freeze_thaw_boundary` | PASS (fixture) |
| URS-16 to URS-21 assay processing | H/M | DE modules (DESIGN 4) | DE `test_ingest.py`, `test_curve.py`, `test_qc.py`, `test_reportable.py`, `test_outputs.py` | PENDING (DE) |
| URS-22 one config | M | `config/qc_rules.yaml`, `pipeline/config.py` | DE config test (`dbt_vars` keys) | PENDING (DE) |
| URS-23 immunogenicity | M | `pipeline/stats.py`, `mart_immunogenicity` | LIA `test_stats.py`, `test_kpis.py` | PENDING (LIA) |
| URS-24 KPIs | L | `mart_lab_kpis` | LIA `test_kpis.py` | PENDING (LIA) |
| URS-25 reproducible generator | M | `generator/generate.py` | DE `test_generator.py` | PENDING (DE) |
| URS-26 scorecard recall | M | `detection_scorecard` | LIA `test_scorecard.py` | PENDING (LIA) |
| URS-27 exports and charts | L | `export.py`, `charts.py` | LIA tests | PENDING (LIA) |
| URS-28 one command | L | `pipeline/run.py`, OPS | smoke run, QA-02 | PENDING |
