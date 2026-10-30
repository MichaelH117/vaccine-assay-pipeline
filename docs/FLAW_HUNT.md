# Flaw hunt

Owner: Principal Engineer seat. Date: 2026-10-30. Build checked: seed 42, rule version QC-RULES-1.0, the state
recorded in [results.json](results.json) (pytest 245 passed, 0 failed; dbt 145 of 145). All data is synthetic.

Method: for each known way a data pipeline goes wrong, try to make it happen, and record what happened with a test
name, a file, or a command and its real output. **Status** is one of: *Handled* (the failure mode is covered, with
evidence), *Found, fixed* (it was a real defect and is fixed), *Found, open* (real defect, logged for its owner),
*Limitation* (real, accepted for a demo, listed in [KNOWN_ISSUES.md](KNOWN_ISSUES.md)), or *Not applicable* (with
the reason). Nothing below is "not checked".

| ID | Failure mode | Status | Evidence |
|---|---|---|---|
| FH-01 | Duplicates or drift on re-run (idempotency) | Handled; re-verified today | Two runs, 58 of 60 output files byte-identical; the 2 others differ only in run-clock columns |
| FH-02 | Late-arriving data | Handled for records, Limitation for files | INJ-4 LATE_ENTRY; full rebuild only |
| FH-03 | Silent schema drift | Found, open (BUG-011) | A dropped landing column loads as NULL |
| FH-04 | Tests that cannot fail | Handled; 1 weak spot found, open (BUG-010) | 3 planted bugs |
| FH-05 | Metric gaming | Handled | FP rates, masking rule, hand-written answer key |
| FH-06 | PII handling | Not applicable (no PII exists), guarded by a test | `test_ids_are_synthetic_patterns_only` |
| FH-07 | Time zones | Handled for audit times, Limitation for lab times | UTC audit clock; lab times have no zone |
| FH-08 | Floating-point and edge values | Found, fixed (BUG-001, BUG-002, F8) | inf, NaN, out-of-range OD, boundary tests |
| FH-09 | A killed run leaves mixed state | Found, open (Limitation) | DE's run killed for low memory, 2026-10-30 |
| FH-10 | Test harness drifts from the real pipeline | Found, fixed (see postmortem) | `pipeline.run.integrity_step` is shared |

---

## FH-01. Duplicates or drift on re-run (re-verified 2026-10-30)

**Why it matters.** If a second run with the same seed changes any number, no reported result can be reproduced, and
a rerun can double-count rows.

**What I did.** Two back-to-back runs of `.venv/Scripts/python -m pipeline.run` (seed 42, no `--test`; 12.3 s and
10.6 s). After each one, `sh tools/hash_outputs.sh` hashed every output: 21 landing CSVs (8 LIMS and manifest files plus 13 plate files), 13 read-only raw copies,
20 mart exports (CSV + Parquet), the DuckDB file, the audit anchor, `docs/results.json` and the 3 chart PNGs.
The hash lists are kept in [evidence/repeat_run1.sha256](evidence/repeat_run1.sha256) and
[evidence/repeat_run2.sha256](evidence/repeat_run2.sha256).

**Result.**
- **58 of 60 files are byte-identical**, including every mart export, all 3 PNGs and `docs/results.json`.
  `docs/results.json` is also byte-identical to the copy from before this check.
- The 2 that differ are `data/warehouse/vaccine_assay.duckdb` and `data/warehouse/audit_anchor.json`. Both hold
  wall-clock times of the run (`audit_ts_utc`, `written_at_utc`), so they cannot be identical.
- To prove nothing else differs, a third and fourth run were compared table by table with
  `tools/compare_duckdb_runs.py`: **37 tables; 30 identical; 7 differ only in run-clock columns; 0 other
  differences.** The 7 are `audit.audit_log` (timestamps, hashes, and the payloads of the 13 `lims.raw_files` rows,
  which contain `ingested_at`), `audit.audited_tables`, `audit.chain_checkpoint`, `audit.chain_verify`,
  `audit.file_integrity`, `audit.record_reconciliation` and `lims.raw_files`. Same audit row count, and the same
  table, key and action at every `audit_seq`.

**Other guards.**
- `tests/test_outputs.py::test_rebuild_is_deterministic`: 10 core and mart tables equal across two builds.
- `tests/qa/test_qa_run_edges.py::test_rerun_on_existing_folder_gives_same_result`.
- `tests/test_generator.py::test_same_seed_gives_byte_identical_files`.
- Re-inserting a key is refused, not overwritten: `tests/test_audit.py::test_reinsert_same_key_is_refused_no_silent_overwrite`.
- A second upload of the same plate file is logged, not counted twice (BUG-006, fixed):
  `tests/qa/test_qa_pipeline_edges.py::test_duplicate_upload_does_not_double_count`, `::test_duplicate_upload_is_reported`.

**Limitation.** Each run rebuilds `data/` from scratch, which also deletes the previous audit trail. That is fine for
a reproducible demo and would be record destruction in a real lab (KNOWN_ISSUES KI-01).

## FH-02. Late-arriving data

- **Late records (handled).** A custody event recorded more than 24 h after it was performed raises ALCOA-C1
  LATE_ENTRY. Planted as INJ-4 (EVT-001077, recorded 30.0 h late) and caught on seed 42.
  Tests: `tests/test_alcoa.py::test_late_entry_boundary_is_strictly_greater_than_limit`, `::test_inj4_late_entry_detected_on_build`.
- **Out-of-order custody (handled):** `tests/qa/test_qa_pipeline_edges.py::test_custody_out_of_order_flagged`,
  `::test_custody_out_of_order_not_a_gap`.
- **A later repeat run of a sample (handled):** the latest *valid* run wins, and a later invalid run never replaces an
  earlier valid one. `tests/test_reportable.py::test_later_invalid_run_does_not_replace_earlier_valid_run`.
- **A plate file that arrives after the run (limitation).** Its samples show in `core.missing_results` as not
  assayed, so they are not lost. But there is no incremental load: calling `ingest_plates` twice raises
  `AppendOnlyError` (BUGS.md, Observations), so the only way in is a full rebuild. KNOWN_ISSUES KI-01.

## FH-03. Silent schema drift (found, open: BUG-011)

**Plate files.** The parser accepts only an 8 x 12 grid labelled A-H and 1-12, and names the problem when the labels are
wrong (BUG-008, fixed). Tests: `tests/test_ingest.py::test_7x12_file_is_rejected`,
`tests/qa/test_qa_parser.py::test_malformed_file_rejected_cleanly`, `::test_utf16_file_rejected_cleanly`,
`::test_label_error_message_names_the_labels`.

**Landing CSVs (LIMS tables).** `PYTHONPATH=. .venv/Scripts/python tools/schema_drift_probe.py` changes one header per
case on a temp copy and loads it. Real output:

```
extra column on samples.csv: REJECTED -> ValueError: columns ['new_col'] are not in lims.samples
dropped column subjects.site_id: ACCEPTED SILENTLY
renamed custody performed_by->operator: REJECTED -> ValueError: columns ['operator'] are not in lims.custody_events
```

A dropped non-key column loads as NULL for every row, and no dbt test checks `stg_subjects.site_id`. Logged as
**BUG-011** (Medium, data-engineer) in [team/BUGS.md](team/BUGS.md), with a fix hint.

## FH-04. Tests that cannot fail (proved with planted bugs)

Each mutation was made in the working copy, the named tests were run, and the file was restored from a copy taken
first (`cmp` confirmed it was byte-identical afterwards, and the tests passed again).

| # | Planted bug | Tests run | Result with the bug | After restore |
|---|---|---|---|---|
| a | `pipeline/qc.py:70`: DUP_CV fires only above 10 x the limit (`> max_cv * 10`) | `tests/test_qc.py::test_dup_cv_boundary_and_blocking` | **1 failed** in 0.15 s | 1 passed |
| b | `pipeline/audit.py:496`: reconciliation no longer reports RECORD_MODIFIED | `tests/test_audit.py::test_base_row_edit_is_found_with_field_diff`, `tests/qa/test_qa_audit_chain.py::test_base_table_edit_detected` | **2 failed** in 0.29 s | 2 passed |
| c | `generator/generate.py:321-322`: INJ-11 removed from the manifest (so it is never planted) | `tests/test_generator.py`, `tests/test_scorecard.py`, `tests/test_alcoa.py`, `tests/test_audit.py` | **69 passed** in 28.59 s: nothing failed | n/a |
| c2 | same bug | `tests/qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp`, `tests/qa/test_qa_pipeline_edges.py::test_planted_problems_still_100pct_recall` | **6 failed, 1 passed** in 100.71 s | n/a |

Finding from (c): the seat-level recall test and the hand-written answer key cover INJ-1..8 only, so a lost INJ-11 is
caught only by QA's slow seed sweep. The full suite still goes red, so this is Low. Logged as **BUG-010** for the Lab
Informatics Analyst (it is the INJ-11 recall test that the GxP seat requested). Earlier, the Tech Lead found one scorecard
test that could never fail (REVIEW F6); LIA replaced it with a hand-written answer key and three sandbox tests in
which INJ-5 must *stop* being detected when its control flag is removed or a curve failure is added
(`tests/test_scorecard.py::test_inj5_not_detected_without_ctrl_oor`, `::test_inj5_not_detected_when_curve_also_failed`).

QA's open bugs were each guarded by an `xfail(strict=True)` test, so a fix had to switch its test on (BUGS.md header).

## FH-05. Metric gaming

The headline metric is recall: "13 of 13 required planted problems caught". It could be gamed in four ways:
1. **Flag everything.** Recall would be 100% and useless. Guard: the false-positive rates are reported next to it,
   per sample (1 of 360, 0.277%) and per plate (0 of 13 rejected without a planted cause).
   `tests/test_scorecard.py::test_false_positive_rate_reported_and_within_target`, `::test_rejected_plates_are_exactly_the_injected_plates`.
2. **Get caught for the wrong reason.** A plate with a broken curve also failed its controls, so INJ-5 ("control off,
   curve fine") could score without the control rule working (REVIEW F3). Guard: masking rule plus the sandbox tests in FH-04.
3. **Count records instead of problems.** INJ-2 is one swap that touches two samples. The headline counts problems
   (13) and lists records (14) separately. `tests/test_scorecard.py::test_summary_counts_problems_not_keys`.
4. **Shrink the required list.** `scorecard.required_inj_types` lives in the versioned config. The headline also prints
   the optional count, so a type moved out of "required" still shows up. Residual risk: R-07 in [RISK_REGISTER.md](RISK_REGISTER.md).

**The one unexplained flag is left visible on purpose.** The single "false positive" is SMP-00180: RECORD_MISMATCH,
raised because INJ-7 tampers with that sample's audit payload, so reconciliation also notices it (ADR 007). It is a
true second detection, not noise. We could reach 0% by adding RECORD_MISMATCH to INJ-7's expected flags, but that
would change the answer key to fit the result. It stays at 0.277%, and the reason is written down here.

## FH-06. PII handling (not applicable, guarded)

There is no personal data to protect. Subjects are `SUBJ-0001` with group and site only; users are "Lab Tech 01"
style display names; no names, birth dates, contact details or medical record numbers exist in any landing file
(checked: the headers of `subjects.csv`, `users.csv`, `samples.csv`, `custody_events.csv`).
`tests/test_generator.py::test_ids_are_synthetic_patterns_only` fails if an ID stops matching its synthetic
pattern. A real deployment would hold coded subject IDs only, with the key held by the clinical site (OPERATING_MODEL.md).

## FH-07. Time zones

- **Audit times (handled):** every audit, checkpoint, ingest and anchor time comes from `datetime.now(UTC)` and is
  stored as naive UTC (`pipeline/audit.py::_utc_now`, DESIGN section 3). The anchor in this run says
  `"written_at_utc": "2026-10-30T04:48:11..."`, which is UTC, not local time (local was 00:48 EDT).
- **Lab times (limitation):** `performed_at`, `recorded_at`, `collected_at` and `run_at` in the landing CSVs carry no
  zone. LATE_ENTRY compares two of them in the same frame, so a 24 h limit spanning a daylight-saving change could be
  off by one hour. The synthetic generator emits wall-clock times without DST, so seed 42 cannot hit it.
  KNOWN_ISSUES KI-05 says what would fix it.

## FH-08. Floating-point and edge values (found, fixed)

| Case | Outcome | Test |
|---|---|---|
| `inf`, `-inf`, `Infinity` in an OD cell aborted the whole run (BUG-001, High) | Fixed: the plate is rejected and logged, the run continues | `tests/qa/test_qa_run_edges.py::test_infinite_od_does_not_abort_run`, `tests/qa/test_qa_parser.py::test_infinite_od_rejected` |
| Negative or 1e300 OD accepted (BUG-002) | Fixed: reader range in config, 0.0 to 4.5 | `tests/qa/test_qa_parser.py::test_implausible_od_rejected` |
| NaN mean OD labelled IN_RANGE with a null concentration (REVIEW F8) | Fixed: no range label | `tests/test_curve.py::test_nan_mean_od_gets_no_label` |
| 4PL fit stuck at a parameter bound counted as converged (REVIEW F4) | Fixed: `converged=False` | `tests/test_curve.py::test_fit_stuck_at_a_bound_is_not_converged` |
| Threshold boundaries (R² 0.98, recovery fraction, control ±20%, blank, CV 20%) | Inclusive/exclusive as the config says | `tests/test_qc.py::test_*_boundary` (5 tests) |
| 0 of n and n of n seroresponse CIs | Exact Clopper-Pearson edges | `tests/test_stats.py::test_clopper_pearson_zero_of_n`, `::test_clopper_pearson_n_of_n` |
| Baseline exactly at LLOQ, exactly 4-fold rise | Rule applied as written | `tests/test_stats.py::test_seroresponse_baseline_exactly_at_lloq_is_fold_rule`, `tests/test_kpis.py::test_build_rows_pairs_subjects_and_nulls_baseline` |
| Zero or negative concentration into a geometric mean | Rejected loudly | `tests/test_stats.py::test_gmt_rejects_non_positive`, `tests/qa/test_qa_immunogenicity_edges.py::test_zero_value_rejected_loudly` |
| Type round-trip making reconciliation see false edits | Fixed: the audit stores the row as read back (DV-05); a clean build reconciles | `tests/test_audit.py::test_audit_payload_is_the_stored_row`, `::test_clean_load_reconciles` |
| Single-well sample (duplicate missing) gets CV = NaN, so no precision check | Open, product call | BUGS.md Observations; KNOWN_ISSUES KI-07 |

## FH-09. A killed run leaves mixed state (found, open)

`build()` deletes `data/` first and rebuilds it in place. On 2026-10-30 the operating system killed a full run for
low memory (HANDOFF, DE entry: "`data/` in the repo may be partial until the next run"). In that state
`docs/results.json` still describes the previous complete run, while `data/` is half built. Nothing marks the
folder as incomplete. Fix: build into `data.tmp/` and rename it over `data/` only after dbt passes, and write
results.json last. KNOWN_ISSUES KI-02; ROADMAP "Next".

## FH-10. Test harness drifts from the real pipeline (found, fixed)

QA's `staged_build` helper had copied `build()` step 7 by hand, so it never called `tamper_base_row`; INJ-11 was in
the manifest but never planted in staged builds. Fixed by making `pipeline.run.integrity_step` the only step 7,
called by both. Full write-up: [POSTMORTEM_2026-10-30_INJ11_harness_drift.md](POSTMORTEM_2026-10-30_INJ11_harness_drift.md).
