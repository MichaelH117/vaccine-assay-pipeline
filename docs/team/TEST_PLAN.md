# TEST PLAN: vaccine-assay-pipeline

Owner: QA seat (QA-01). 2026-10-30. Maps every acceptance criterion in SPEC.md section 4 to the test(s) that prove it.
Paths are relative to `tests/`. `dbt:` means a dbt data test that runs inside `dbt build` (131 nodes, 99 tests).
QA edge tests live in `tests/qa/` and are listed with the AC they push on. Open bugs are in `BUGS.md`.

**Status key:**
- **MET**: a passing automated test proves it.
- **MET (manual)**: proved by a recorded manual check, with no automated test.
- **PARTIAL**: the core claim is tested, but a QA edge case exposed a gap (named bug).
- **NOT MET**: the criterion is not satisfied today.

**Last full run (2026-10-30):** `.venv\Scripts\python -m pytest -q -p no:cacheprovider` -> **196 passed, 14 xfailed,
0 failed** (181 s). That is 131 seat tests + 79 QA tests (65 pass + 14 strict-xfail = the open bugs). dbt build
inside every fixture: 131 of 131 passed.

## How to run
- Everything: `.venv\Scripts\python -m pytest -q -p no:cacheprovider` (about 3 min; the 6-seed sweep is about 75 s of it).
- QA only: `.venv\Scripts\python -m pytest tests/qa -q -p no:cacheprovider`
- Builds go to pytest tmp folders. Nothing in the tests touches the repo's `data/`.

## Traceability: AC -> test

### US-1 Generator
| AC | Test(s) | Status |
|---|---|---|
| 1.1 same seed, byte-identical (SHA-256) | test_generator.py::test_same_seed_gives_byte_identical_files, ::test_files_use_lf_line_endings; test_outputs.py::test_rebuild_is_deterministic | MET |
| 1.2 subjects, samples, custody, plate maps, 8x12 CSVs | test_generator.py::test_plate_layout; test_outputs.py::test_landing_rows_tie_out_to_lims_and_staging | MET |
| 1.3 injected_problems.csv has INJ-1..8 | test_generator.py::test_every_required_inj_type_is_in_the_manifest, ::test_planted_problems_are_where_the_manifest_says; qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp (8 types on 6 seeds) | MET |
| 1.4 clean Vaccine D29 GMT >= 4x baseline; Placebo GMFR 0.8-1.25 | test_generator.py::test_clean_effect_sizes_from_true_concentrations; test_outputs.py::test_clean_build_marts_show_vaccine_effect | MET |
| 1.5 synthetic IDs, no real names | test_generator.py::test_ids_are_synthetic_patterns_only | MET |

### US-2 Mini-LIMS and custody
| AC | Test(s) | Status |
|---|---|---|
| 2.1 samples, aliquots, custody_events tables with the listed columns | test_outputs.py::test_landing_rows_tie_out_to_lims_and_staging; DDL in pipeline/schema.py | MET |
| 2.2 step order, `v_custody_status`, custody_complete | test_custody.py::test_custody_status_on_fixture, ::test_in_progress_sample_has_no_gap_flag | MET |
| 2.3 CUSTODY_GAP names the missing step | test_custody.py::test_inj3_flagged_with_received_missing, ::test_multiple_missing_steps_listed_in_order | MET |
| 2.4 CUSTODY_ORDER | test_custody.py::test_custody_flags_on_fixture, ::test_repeat_assay_after_stored_is_not_out_of_order; **qa/test_qa_pipeline_edges.py::test_custody_out_of_order_flagged, ::test_custody_out_of_order_not_a_gap** (first test on a real build) | MET |
| 2.5 FREEZE_THAW_EXCEEDED > 2 | test_custody.py::test_freeze_thaw_boundary; test_generator.py::test_optional_problems_add_inj_9_and_10 | MET |

### US-3 Audit trail and ALCOA+
| AC | Test(s) | Status |
|---|---|---|
| 3.1 every insert writes who/what/when/why | test_audit.py::test_insert_writes_data_and_one_audit_row_per_record, ::test_every_base_table_row_has_an_insert_audit_row, ::test_who_and_why_are_required; test_ingest.py::test_every_insert_is_audited; qa/test_qa_audit_chain.py::test_blank_who_or_why_refused | MET |
| 3.2 corrections are new rows; no API update/delete | test_audit.py::test_update_and_delete_always_raise, ::test_correction_appends_row_pointing_to_superseded_row, ::test_reinsert_same_key_is_refused_no_silent_overwrite; qa/test_qa_audit_chain.py::test_api_has_no_update_or_delete, ::test_reinsert_existing_key_refused_and_atomic | MET |
| 3.3 hash chain; verify names the first broken row (INJ-7) | test_audit.py::test_direct_sql_update_breaks_chain_at_that_row, ::test_chain_broken_exactly_at_inj7_on_build, ::test_rehashed_forgery_still_breaks_at_next_row; qa/test_qa_audit_chain.py::test_direct_edit_detected_at_that_row[1,3,6] (first/middle/last), ::test_middle_row_deleted_detected, ::test_rows_swapped_detected | PARTIAL: the AC as written is MET. Tail deletion or tail re-hash goes undetected (**BUG-004**). A base-table edit is invisible (**BUG-005**). |
| 3.4 alcoa_findings: Attributable, Contemporaneous, Original, Complete | test_alcoa.py::test_alcoa_findings_on_fixture (A1, A2, C1, O1, CM1), ::test_inj4_late_entry_detected_on_build, ::test_late_entry_boundary_is_strictly_greater_than_limit | MET |
| 3.5 raw CSVs copied read-only, SHA-256 stored, never changed | test_alcoa.py::test_raw_files_are_read_only, ::test_edited_raw_file_gives_mismatch, ::test_raw_files_match_on_build; test_ingest.py::test_raw_copies_are_read_only_and_hashed; qa/test_qa_run_edges.py::test_raw_file_edited_after_ingest_caught_then_rebuild_restores (edit and delete after ingest) | MET |

### US-4 Ingestion
| AC | Test(s) | Status |
|---|---|---|
| 4.1 96 rows; wrong shape rejected, logged, no crash | test_ingest.py::test_good_file_gives_96_rows, ::test_7x12_file_is_rejected, ::test_bad_file_is_logged_and_run_continues; qa/test_qa_parser.py (13 malformed variants + utf-16 rejected cleanly), qa/test_qa_run_edges.py::test_empty_plate_file_logged_and_run_continues, qa/test_qa_pipeline_edges.py::test_truncated_plate_logged_not_crashed | PARTIAL: one `inf` cell crashes the whole run (**BUG-001**, High). Implausible OD is accepted (BUG-002). A duplicate file is silent (BUG-006). The error text is misleading (BUG-008). |
| 4.2 well_type, nominal conc, sample_id + dilution | test_generator.py::test_plate_layout; test_ingest.py::test_inj2_gives_exactly_two_id_mismatch_flags (join) | MET |
| 4.3 blank-corrected OD | test_ingest.py::test_blank_correction | MET |
| 4.4 ID_MISMATCH vs LIMS assayed event (INJ-2) | test_ingest.py::test_inj2_gives_exactly_two_id_mismatch_flags; **qa/test_qa_pipeline_edges.py::test_unknown_sample_id_flagged, ::test_unknown_sample_id_never_reported, ::test_displaced_lims_sample_not_silently_dropped** | MET |

### US-5 4PL fit
| AC | Test(s) | Status |
|---|---|---|
| 5.1 4PL per plate, a-d, R2, convergence stored | test_curve.py::test_non_converging_input_returns_converged_false; qa/test_qa_pipeline_edges.py::test_all_standards_failed_plate_has_no_working_range | MET |
| 5.2 no-noise c within 1% | test_curve.py::test_no_noise_fit_recovers_c_within_1pct | MET |
| 5.3 % recovery per standard | test_curve.py::test_bad_standard_fails_recovery | MET |
| 5.4 inverse-4PL x dilution; no extrapolation | test_curve.py::test_inverse_of_four_pl_is_identity, ::test_inverse_outside_asymptotes_is_nan, ::test_out_of_range_od_gets_labels_and_no_extrapolation | MET |
| 5.5 LLOQ/ULOQ = contiguous passing run | test_curve.py::test_working_range_is_longest_contiguous_run | MET |

### US-6 QC
| AC | Test(s) | Status |
|---|---|---|
| 6.1 FIT_FAIL, STD_RECOVERY, CTRL_OOR, BLANK_HIGH | test_qc.py::test_fit_fail_boundary, ::test_std_recovery_boundary, ::test_ctrl_oor_boundary, ::test_blank_high_boundary; qa/test_qa_pipeline_edges.py::test_all_standards_failed_plate_rejected; qa/test_qa_run_edges.py::test_all_blank_plate_rejected_without_crash | MET |
| 6.2 any plate flag means REJECTED; samples excluded and re-assayed | test_qc.py::test_any_plate_flag_means_rejected, ::test_inj1_and_inj5_plates_rejected; test_outputs.py::test_rejected_plate_samples_on_reassay_list; qa/test_qa_pipeline_edges.py::test_all_standards_failed_samples_not_reported_and_reassayed | PARTIAL: a plate whose file could not be parsed never gets a status, and its samples never reach the re-assay list (**BUG-003**). |
| 6.3 DUP_CV, BELOW/ABOVE_LLOQ/ULOQ, ID_MISMATCH | test_qc.py::test_dup_cv_boundary_and_blocking, ::test_range_flags_on_accepted_plates_only; test_ingest.py::test_inj2_... | MET |
| 6.4 ABOVE_ULOQ with higher dilution and DUP_CV on the re-assay list | test_outputs.py::test_inj8_reassay_at_higher_dilution_then_reported; test_reportable.py::test_every_repeated_sample_was_on_the_reassay_list | MET |
| 6.5 rule_id, version, value, threshold per flag | test_qc.py::test_every_flag_has_version_value_or_threshold | MET |

### US-7 Reportable results
| AC | Test(s) | Status |
|---|---|---|
| 7.1 one row per sample, ACCEPTED only | dbt: unique/not_null/relationships on fct_reportable_result.sample_id; test_outputs.py::test_reportable_only_from_accepted_plates_without_blocking_flags; qa/test_qa_pipeline_edges.py::test_duplicate_upload_does_not_double_count | MET |
| 7.2 latest valid run, reason in audit | test_reportable.py::test_latest_valid_run_wins_with_reason, ::test_later_invalid_run_does_not_replace_earlier_valid_run, ::test_selection_is_in_the_audit_trail | MET |
| 7.3 `<LLOQ` with 0.5 x LLOQ | test_outputs.py::test_below_lloq_imputation; test_reportable.py::test_below_lloq_is_reportable_but_blocked_flags_are_not | MET |
| 7.4 missing_results with a reason, never silently dropped | test_outputs.py::test_every_sample_in_reportable_or_missing_never_both, ::test_inj2_samples_are_missing_with_reason; dbt: assert_reportable_and_missing_disjoint; qa/test_qa_pipeline_edges.py::test_every_sample_reportable_xor_missing, ::test_truncated_plate_samples_listed_as_missing | MET. No sample is dropped, but the reason given for an unparseable plate is wrong (`NOT_ASSAYED`, BUG-003). |

### US-8 Immunogenicity
| AC | Test(s) | Status |
|---|---|---|
| 8.1 one row per group x visit, n, GMT, t-based CI | test_kpis.py::test_gmt_matches_recompute; dbt: unique on group_visit_key; qa/test_qa_immunogenicity_edges.py::test_single_subject_group_has_point_but_no_ci, ::test_all_subjects_below_lloq | MET |
| 8.2 GMFR only on paired subjects | test_kpis.py::test_gmfr_and_seroresponse_use_paired_subjects_only; test_stats.py::test_gmfr_is_paired_not_ratio_of_gmts; **qa/test_qa_immunogenicity_edges.py::test_baseline_only_subject_excluded_from_gmfr_but_in_gmt, ::test_post_only_subject_excluded_from_gmfr, ::test_group_with_no_paired_subjects_gives_nulls_not_crash** | MET |
| 8.3 seroresponse n/N, Clopper-Pearson | test_stats.py::test_seroresponse_* (5 tests), ::test_clopper_pearson_* (4 tests); qa/test_qa_immunogenicity_edges.py::test_below_lloq_baseline_needs_4x_lloq_not_4x_imputed | MET |
| 8.4 hand-calculated 5-subject GMT/GMFR | test_stats.py::test_gmt_hand_calculated_5_subjects, ::test_gmfr_hand_calculated_5_subjects | MET |
| 8.5 Vaccine D29 seroresponse > Placebo | test_kpis.py::test_vaccine_d29_seroresponse_beats_placebo | MET |

### US-9 Lab KPIs
| AC | Test(s) | Status |
|---|---|---|
| 9.1 TAT median/p90, plate failure rate + reasons, re-assay rate, custody %, ALCOA per 100 | test_kpis.py::test_mart_has_every_kpi and one test per KPI; qa/test_qa_deliverables.py::test_spec_kpis_all_present | MET |
| 9.2 every KPI defined in METRICS.md | **qa/test_qa_deliverables.py::test_every_kpi_id_is_defined_in_metrics_md** (new). Whether each definition matches the SQL was checked by hand for REASSAY_RATE, PLATE_FAIL_RATE and ALCOA_FINDINGS_PER_100. | MET (names automated; formulas spot-checked by hand) |
| 9.3 KPI values match a pytest recompute | test_kpis.py (6 recompute tests) | MET |

### US-10 Detection scorecard
| AC | Test(s) | Status |
|---|---|---|
| 10.1 joins truth to flags, detected yes/no + catching flag | test_scorecard.py::test_scorecard_has_one_row_per_injected_key, ::test_detected_rows_name_an_expected_flag | MET |
| 10.2 100% recall INJ-1..8 on the default seed | test_scorecard.py::test_recall_is_100pct_for_inj_1_to_8; **qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp[0,1,2,3,2^32-1,10^12]**; qa/test_qa_pipeline_edges.py::test_planted_problems_still_100pct_recall (with 5 extra QA problems added) | MET |
| 10.3 FP counted, <= 5% | test_scorecard.py::test_false_positive_rate_reported_and_within_target; qa seed sweep (FP 0.0% on all 6 seeds) | MET |

### US-11 Dashboard spec and outputs
| AC | Test(s) | Status |
|---|---|---|
| 11.1 3 pages with the named visuals | **qa/test_qa_deliverables.py::test_dashboard_spec_has_three_pages_and_named_visuals** | MET |
| 11.2 each visual names mart, fields, filters, DAX | qa/test_qa_deliverables.py (the test only checks that `data/marts/` and `DAX` are mentioned); a full read-through is in the DASHBOARD_SPEC "Acceptance check" section | MET (manual) |
| 11.3 marts exported to data/marts/ | **qa/test_qa_deliverables.py::test_exports_write_csv_and_parquet_that_tie_out** (CSV rows = Parquet rows = mart rows) | MET |
| 11.4 3 PNG charts | **qa/test_qa_deliverables.py::test_three_png_charts_rendered** | MET |

### US-12 One command
| AC | Test(s) | Status |
|---|---|---|
| 12.1 one documented command, < 5 min | Manual run: `.venv\Scripts\python -m pipeline.run` took 11.7 s (2026-10-30). With `--test`, add about 3 min of pytest. `README.md` does not exist, so the command is not documented yet. | **NOT MET** (the command works, but documenting it is OPS-01, BUG-009) |
| 12.2 pytest and dbt test 0 failures, output in HANDOFF | the full suite above; dbt 131/131 | MET |
| 12.3 pinned deps, no secrets, no network | `requirements.txt` is unpinned (BUG-009). No secrets found by inspection. No network check is automated. | **NOT MET** (pinning is OPS-01) |

## Edge cases asked for, and where they live
| Case | Test | Result |
|---|---|---|
| Plate where every standard fails | qa/test_qa_pipeline_edges.py (FLAT) | pass: REJECTED, no working range, all 37 samples re-assayed |
| Malformed / truncated / empty CSV | qa/test_qa_parser.py; qa/test_qa_pipeline_edges.py (TRUNC); qa/test_qa_run_edges.py::test_empty_plate_file_... | pass, except BUG-001 (`inf`) and BUG-003 (no re-assay) |
| Sample ID not in the LIMS | qa/test_qa_pipeline_edges.py (GHOST) | pass |
| Duplicate plate upload | qa/test_qa_pipeline_edges.py (DUP); qa/test_qa_audit_chain.py::test_reinsert_existing_key_refused_and_atomic | no double counting, but the upload goes silent (BUG-006) |
| Custody step out of order | qa/test_qa_pipeline_edges.py (ORDER) | pass |
| Baseline but no post visit | qa/test_qa_immunogenicity_edges.py | pass |
| All subjects below LLOQ | qa/test_qa_immunogenicity_edges.py::test_all_subjects_below_lloq | pass |
| Unusual seeds | qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp, ::test_invalid_seed_... | pass on 6 seeds. A negative seed wipes data (BUG-007) |
| Re-run on an existing DB/folder | qa/test_qa_run_edges.py::test_rerun_on_existing_folder_gives_same_result | pass (identical counts, raw files still read-only) |
| Audit row tampered: middle vs last | qa/test_qa_audit_chain.py | an edit of the middle or last row is caught at that row. Tail delete or tail re-hash is not caught (BUG-004) |
| Raw file edited after ingest | qa/test_qa_run_edges.py::test_raw_file_edited_after_ingest_... | pass (edit and delete both caught) |
| All-blank plate | qa/test_qa_run_edges.py::test_all_blank_plate_rejected_without_crash | pass |
| Sample with only one well | not automated | Observation in BUGS.md: reportable with no CV check (PO call) |

## Not covered
- Running on a clean machine with no network access: that is OPS-01's job.
- Runtime with a large study (thousands of samples): not in scope for v1.
