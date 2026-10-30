# DEMO SIGN-OFF: vaccine-assay-pipeline

Owner: Product Owner seat. Date: 2026-10-30. Commit reviewed: c3a93fd (local, not pushed).
Method: I read the outputs only. I did not re-run the pipeline or pytest.
Sources: `docs/results.json` (seed 42, QC-RULES-1.0), `data/marts/*.csv`, `docs/img/*.png`,
`docs/evidence/repeat_run_summary.json`, `docs/team/TEST_PLAN.md`, `docs/team/BUGS.md`, `docs/validation/`,
`docs/DASHBOARD_SPEC.md`, `requirements.txt`, `README.md`, and `docs/team/HANDOFF.md`. All data is synthetic.

Final run, as recorded in results.json: pytest **245 passed, 0 failed, 0 skipped, 0 error** (356.12 s, 2026-10-30).
dbt **145 of 145 passed** (34 models, 111 tests, 0 warn). **13 of 13** required planted problems caught (14 of 14 keys).

Caveat: `TEST_PLAN.md` is stale. It still says 196 passed, dbt 131/131, AC-12.1 and AC-12.3 NOT MET, and AC-3.3,
AC-4.1 and AC-6.2 PARTIAL. BUGS.md marks every bug behind those statuses FIXED (BUG-001, 003, 004, 005, 009), and each
fix removed a strict-xfail mark. The final suite has 0 failures, so those tests now pass. I used the newer
evidence. QA should refresh TEST_PLAN.md.

"Tests only" below means the seed-42 demo data does not trigger that rule, so the only evidence is a passing test named in TEST_PLAN.

## Verdict per acceptance criterion

### US-1 Generator
| AC | Verdict | Evidence |
|---|---|---|
| 1.1 | MET | repeat_run_summary.json: 58 of 60 files identical. The 2 that differ are the DuckDB file and the anchor, and only in run-clock columns. All generator outputs are identical. `test_same_seed_gives_byte_identical_files` passes. |
| 1.2 | MET | v_custody_status.csv has 360 samples. 13 plate CSVs. Layout test is in the 245 passing tests. |
| 1.3 | MET | The scorecard in results.json lists INJ-1..8 plus INJ-11. `required_inj_types_planted` = 9 of 9. |
| 1.4 | MET | Clean-data test passes. Even on dirty data, Vaccine D29 GMT is 4332.9 vs D1 258.3 (16.8x), and Placebo GMFR is 0.97 (D29) and 1.00 (D57). |
| 1.5 | MET | IDs are SUBJ-/SMP-/EVT-/PLATE- patterns. `test_ids_are_synthetic_patterns_only` passes. |

### US-2 Mini-LIMS and custody
| AC | Verdict | Evidence |
|---|---|---|
| 2.1 | MET | Tables are tested in test_outputs. The custody_events columns appear in the alcoa_findings details. |
| 2.2 | MET | v_custody_status.csv has 360 rows. CUSTODY_COMPLETE_PCT = 359/360. |
| 2.3 | MET | alcoa_findings: SMP-00164 CUSTODY_GAP, "missing step: received". |
| 2.4 | MET (tests only) | Not planted on seed 42. QA tests pass on a real build: `test_custody_out_of_order_flagged`. |
| 2.5 | MET (tests only) | INJ-9 is optional and not planted on the default run. `test_freeze_thaw_boundary` passes. |

### US-3 Audit trail and ALCOA+
| AC | Verdict | Evidence |
|---|---|---|
| 3.1 | MET | test_audit / test_ingest "every insert audited" tests pass. |
| 3.2 | MET | `test_update_and_delete_always_raise` and `test_api_has_no_update_or_delete` pass. |
| 3.3 | MET | results.json `chain_ok: false`. P-009 (INJ-7, EVT-000924) is caught by AUDIT_CHAIN_BROKEN. The tail gap (BUG-004) is fixed with checkpoints and an anchor. |
| 3.4 | MET | alcoa_findings.csv shows Contemporaneous (LATE_ENTRY EVT-001077, 30 h), Complete (CUSTODY_GAP) and Original (RECORD_MISMATCH x2). Attributable and raw-file Original findings are covered by tests only (`test_alcoa_findings_on_fixture`). |
| 3.5 | MET | `test_raw_files_are_read_only` and `test_raw_file_edited_after_ingest_caught_then_rebuild_restores` pass. |

### US-4 Ingestion
| AC | Verdict | Evidence |
|---|---|---|
| 4.1 | MET | 13 malformed-file variants are rejected. BUG-001 (an `inf` cell aborted the run) is FIXED. `test_infinite_od_does_not_abort_run` passes. |
| 4.2 | MET | Plate-map join tests pass. |
| 4.3 | MET | `test_blank_correction` passes. |
| 4.4 | MET | results.json ID_MISMATCH = 2 (SMP-00257 / SMP-00281, P-002). |

### US-5 4PL fit
| AC | Verdict | Evidence |
|---|---|---|
| 5.1 | MET | PLATE-007 is FIT_FAIL (plate_status_grid.png). curve_fits is tested. |
| 5.2 | MET | `test_no_noise_fit_recovers_c_within_1pct` passes. |
| 5.3 | MET | STD_RECOVERY = 1 on PLATE-007. `test_bad_standard_fails_recovery` passes. |
| 5.4 | MET | BELOW_LLOQ 7 and ABOVE_ULOQ 3 are labelled, not extrapolated. plate_4pl_curve.png shows the working range. |
| 5.5 | MET | `test_working_range_is_longest_contiguous_run` passes. |

### US-6 QC
| AC | Verdict | Evidence |
|---|---|---|
| 6.1 | MET | FIT_FAIL, STD_RECOVERY and CTRL_OOR fire on the demo. BLANK_HIGH is tests only (`test_blank_high_boundary`). |
| 6.2 | MET | 2 of 13 plates REJECTED (PLATE-003, PLATE-007), and repeats PLATE-011 and PLATE-012 are accepted. BUG-003 (unparseable plate) is FIXED. |
| 6.3 | MET | DUP_CV 3, BELOW_LLOQ 7, ABOVE_ULOQ 3, ID_MISMATCH 2. |
| 6.4 | MET | 80 re-assay rows. The INJ-8 samples are re-run at a higher dilution (`test_inj8_reassay_at_higher_dilution_then_reported`). |
| 6.5 | MET | `test_every_flag_has_version_value_or_threshold` passes. rule_version is QC-RULES-1.0. |

### US-7 Reportable results
| AC | Verdict | Evidence |
|---|---|---|
| 7.1 | MET | fct_reportable_result has 358 rows. The dbt unique test passes (145/145). |
| 7.2 | MET | `test_latest_valid_run_wins_with_reason` and `test_selection_is_in_the_audit_trail` pass. |
| 7.3 | MET | `test_below_lloq_imputation` passes. |
| 7.4 | MET | 358 reportable + 2 missing = 360. The 2 missing are the swapped pair, each with a reason. |

### US-8 Immunogenicity
| AC | Verdict | Evidence |
|---|---|---|
| 8.1 | MET | mart_immunogenicity has 6 rows (2 groups x 3 visits) with n, GMT and CI. |
| 8.2 | MET | GMFR for D29/D57 uses paired n (Vaccine D29 gmfr_n 58). |
| 8.3 | MET | Vaccine D29 seroresponse 56/58 = 96.6% (CI 88.1-99.6), Clopper-Pearson. |
| 8.4 | MET | `test_gmt_hand_calculated_5_subjects` and `test_gmfr_hand_calculated_5_subjects` pass. |
| 8.5 | MET | Vaccine D29 is 96.6% vs Placebo D29 0.0%. |

### US-9 Lab KPIs
| AC | Verdict | Evidence |
|---|---|---|
| 9.1 | MET | mart_lab_kpis.csv has TAT median 12.39 d and p90 15.95 d, plate failure rate 15.4% plus per-reason rows, re-assay rate 22.2%, custody complete 99.7%, and ALCOA 0.21 per 100. |
| 9.2 | PARTIAL | Every KPI name is in METRICS.md (automated test). Only 3 of the 11 formulas (REASSAY, PLATE_FAIL, ALCOA) were checked against the SQL by hand. Also, the ALCOA denominator is custody-event records only, which is narrower than the spec's "records". |
| 9.3 | MET | 6 recompute tests in test_kpis pass. |

### US-10 Detection scorecard
| AC | Verdict | Evidence |
|---|---|---|
| 10.1 | MET | detection_scorecard.csv has 14 rows (one per key), with detected and caught_by. |
| 10.2 | MET | required_recall_pct 100.0. missed_problem_ids is empty. Recall is also 100% on a 6-seed sweep. |
| 10.3 | MET | 1 of 360 samples (0.28%) is flagged with no planted cause, against a 5% target. That sample is SMP-00180, a side effect of INJ-7, and it is reported, not hidden. 0 plates were rejected without a planted cause. |

### US-11 Dashboard spec and outputs
| AC | Verdict | Evidence |
|---|---|---|
| 11.1 | MET | DASHBOARD_SPEC.md has Page 1 (RCD), Page 2 (Levey-Jennings) and Page 3 (custody funnel). A QA test passes. |
| 11.2 | MET (manual) | Every visual names its mart, fields and DAX. The automated test only checks keywords. |
| 11.3 | MET | data/marts/ has 10 marts as CSV + Parquet. Row counts match results.json `exports`. |
| 11.4 | MET | gmt_by_group_visit.png, plate_4pl_curve.png and plate_status_grid.png exist. I opened the grid: 11 accepted, 2 rejected. |

### US-12 One command
| AC | Verdict | Evidence |
|---|---|---|
| 12.1 | MET | The README documents `.venv\Scripts\python -m pipeline.run`. Builds took 10.6, 11.0 and 12.3 s, well under 5 min. |
| 12.2 | PARTIAL | 0 failures in pytest and dbt (results.json). The full suite was run by the EM. HANDOFF has no pasted console output for it, only "EM's run: 245 passed". I quoted the results.json summary line in my HANDOFF entry, but that is still not the raw console tail. |
| 12.3 | MET | requirements.txt is pinned (12 packages). No secrets were found in the DevOps staged-file audit. "No network calls" is checked by inspection only. |

**Totals: 51 ACs: 49 MET, 2 PARTIAL, 0 NOT MET.**

## Overall verdict

**ACCEPTED for demo.** Every user story works on the real output. The two PARTIALs are paperwork gaps, not product
gaps. Before the push, fix these (no code changes needed):
1. The EM pastes the raw tail of the final pytest and dbt output into HANDOFF (AC-12.2).
2. QA refreshes TEST_PLAN.md to 245/145 and updates the stale NOT MET and PARTIAL rows.
3. The LIA does a full METRICS.md vs SQL formula check (AC-9.2).
4. SPEC.md still says "DRAFT v1, waiting for Michael". Mark it final and note that INJ-11 became a required type.
5. Make the README fixes listed below.

## Interview talking points (clinical immunology / vaccine R&D data)

1. **"My QC rejected exactly the bad plates and no others."** Each plate gets its own 4PL fit. The working range
   comes from the longest contiguous run of standards with 80-120% back-calculated recovery, and nothing outside it
   is extrapolated. On the demo, 2 of 13 plates were rejected: PLATE-007 (FIT_FAIL + STD_RECOVERY) and PLATE-003
   (CTRL_OOR). Both were planted faults. No plate was rejected without a planted cause, and both were repeated and
   accepted. Proof: `docs/img/plate_status_grid.png` and `mart_plate_qc.csv`.
2. **"Code review showed my audit trail protected the wrong thing, and I fixed it."** The hash chain caught a
   tampered audit row (INJ-7). Review then found that a direct SQL edit of the *record* was invisible to it. I added
   a check that compares every live row with its audited insert payload. A planted re-attribution
   (EVT-000655, USR-04 to USR-01) is now caught as ALCOA+ Original RECORD_MISMATCH. Be honest about the limit: this is detection, not prevention, because DuckDB cannot block a
   direct edit. Proof: ADR 007 and `alcoa_findings.csv`.
3. **"Detection was measured, and the one false positive is shown."** 13 of 13 planted problems were caught across
   9 types. 1 of 360 samples (0.28%) carries a flag with no planted cause, and I traced it to a side effect of INJ-7
   rather than hiding it. The swapped-ID pair is held out of reporting (358 of 360 reportable, 2 listed as missing
   with a reason), not reported with the wrong subject's titer. Proof: `docs/results.json` and `detection_scorecard.csv`.

Do not claim: real LIMS experience, GCLP validation, ICH M10-checked thresholds, or knowledge of which assays or
LIMS Pearl River uses (that is UNVERIFIED in the SPEC).

## README overclaim check

No claims of real deployment, compliance, or years of experience. The README says "not a validated system", "makes no
compliance claim" and "all data is synthetic". Every headline number matches results.json: 13/13, 14/14,
0.277% (truncated), 358/360, 80 re-assay rows, 245 passed, 145/145, 34 models, 111 tests, GMT 4,332 vs 219, CI
3,077-6,100, seroresponse 56/58 vs 0/60, 58/60 and 30/37 identical. These issues need fixing:

1. **Clone URL (lines 96 and 107).** `git clone https://github.com/MichaelH117/vaccine-assay-pipeline.git` is
   written as if the repo is public. It is not pushed, so the command fails today. It becomes true only after
   Michael pushes.
2. **CI claim (line 192).** "CI runs ruff + pytest on every push" is in the "Latest result" column, but CI has never
   run (README limitation 6 and the DevOps HANDOFF entry). Change it to "CI configured; not yet run".
3. **Quickstart timing (line 90).** "About 5 minutes... 1-2 min to install" understates the time. DevOps measured a
   256 s (4.3 min) fresh install, and the line itself adds "about 6 min more" for tests, so the total with tests is
   about 11 min, not 5.
4. **Scale row (line 191).** It says "dbt 137 of 137". That number is from before the BUG-011/012 fixes, and the
   row says so. It is not wrong, but it differs from the 145 headline, so keep the label.
5. **"Detected" wording (minor).** "Is deleting the newest audit rows detected? Yes" is true within one run.
   Limitation 2 says the anchor protects one run only, so link the two.
