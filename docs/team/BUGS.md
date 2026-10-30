# BUGS: vaccine-assay-pipeline

Owner: QA seat. Opened 2026-10-30 from black-box edge testing (`tests/qa/`). Synthetic data only.
Each open bug has a `xfail(strict=True)` test that names it. When the bug is fixed, that test XPASSes, strict mode turns
it into a failure, and the fixer removes the `xfail` mark. That way a fix can't land without its test being switched on.

Severity: **High** = can abort a run or let bad data reach a result. **Medium** = a GxP/AC gap a reviewer
would find. **Low** = a misleading message or a demo limitation.

| ID | Title | Severity | Owner seat | Test |
|---|---|---|---|---|
| BUG-001 | One `inf` OD cell aborts the whole run | High (FIXED) | data-engineer | `test_qa_run_edges.py::test_infinite_od_does_not_abort_run`, `test_qa_parser.py::test_infinite_od_rejected` |
| BUG-002 | Negative or absurd raw OD values are accepted | Low (FIXED) | data-engineer | `test_qa_parser.py::test_implausible_od_rejected` |
| BUG-003 | Samples on an unparseable plate never reach the re-assay list | Medium (FIXED) | data-engineer | `test_qa_pipeline_edges.py::test_truncated_plate_samples_on_reassay_list` |
| BUG-004 | Truncating or re-hashing the tail of the audit chain goes undetected | Medium (FIXED) | gxp-validation-engineer | `test_qa_audit_chain.py::test_last_row_deleted_detected`, `::test_last_row_edit_with_rehash_detected` |
| BUG-005 | A direct edit of a base table (not audit_log) is undetected | Medium (FIXED) | gxp-validation-engineer | `test_qa_audit_chain.py::test_base_table_edit_detected` |
| BUG-006 | A duplicate or unknown plate file is silently ignored | Medium (FIXED) | data-engineer | `test_qa_pipeline_edges.py::test_duplicate_upload_is_reported` |
| BUG-007 | An invalid `--seed` deletes the previous run's data before failing | Medium (FIXED) | data-engineer | `test_qa_run_edges.py::test_invalid_seed_leaves_previous_data_alone` |
| BUG-008 | Wrong row labels give the misleading error "got 8x12" | Low (FIXED) | data-engineer | `test_qa_parser.py::test_label_error_message_names_the_labels` |
| BUG-009 | `requirements.txt` is unpinned and there is no README (AC-12.1, AC-12.3) | Medium | devops-engineer | **FIXED 2026-10-30**: pinned requirements, README Quickstart, Makefile, CI; fresh-venv proof in HANDOFF |
| BUG-010 | Seat-level recall and answer-key tests skip INJ-11 (only the slow seed sweep notices it missing) | Low | analytics-engineer (LIA) | **FIXED 2026-10-30**: `test_scorecard.py::test_inj11_record_edit_is_planted_and_caught` (+ REQUIRED from config) |
| BUG-011 | A landing CSV with a missing non-key column loads silently as NULLs | Medium (FIXED) | data-engineer | `test_ingest.py::test_missing_landing_column_fails_loudly`, `::test_missing_plate_map_column_fails_loudly` |
| BUG-012 | `mart_lab_kpis` has no `PLATE_REJECT_INGEST_ERROR` row | Low | analytics-engineer (LIA) | **FIXED 2026-10-30**: `test_kpis.py::test_plate_failure_rate_and_reasons` |

---

## BUG-001: One `inf` OD cell aborts the whole run (High, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** `parse_plate_csv` rejects non-finite OD (`inf`, `-inf`, `Infinity`); the plate goes to `assay.ingest_errors` and the run continues. xfail mark removed.
- **Steps:** Put `inf` in one sample well of any plate CSV in `landing/plates/` (for example cell A5), then build.
  The test does this through `staged_build` with no dbt.
- **Expected:** AC-4.1 says a bad file is rejected, logged to `assay.ingest_errors`, and the run continues.
- **Actual:** `parse_plate_csv` accepts it, because `pd.to_numeric("inf")` returns `inf`, not NaN. The build then crashes
  in `audit.canonical_json` (`allow_nan=False`) with
  `ValueError: Out of range float values are not JSON compliant: -inf`. The run aborts, and no other plate is processed.
  `-inf` and `Infinity` behave the same way.
- **Fix hint:** in `parse_plate_csv`, treat non-finite values as bad wells (`~np.isfinite(od)`).

## BUG-002: Negative or absurd raw OD values are accepted (Low, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** new config keys `plate.min_raw_od` 0.0 / `plate.max_raw_od` 4.5 (demo defaults, TL to confirm); an OD outside them rejects the file. xfail mark removed.
- **Steps:** Put `-5.0` or `1e300` in a well and call `parse_plate_csv`.
- **Expected:** A raw absorbance outside a plausible reader range (for example 0 to about 4-5 OD) is rejected or
  flagged, because it means a corrupt export.
- **Actual:** The value is accepted. A 1e300 standard would wreck the fit silently, and the QC rules only catch it
  indirectly.
- **Note:** The range belongs in `config/qc_rules.yaml`, so a Tech Lead decision is needed on the limits.

## BUG-003: Samples on an unparseable plate never reach the re-assay list (Medium, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** the plate map of every planned plate is loaded; a planned plate with no usable reads gets a blocking `INGEST_ERROR` plate flag and status REJECTED (counts in plate KPIs); its samples go on `core.reassay_list` (PLATE_REJECTED) and `missing_results.reason = PLATE_INGEST_ERROR`. xfail mark removed.
- **Steps:** Truncate one clean plate CSV half-way, then build. `test_qa_pipeline_edges.py` covers this as the TRUNC case.
- **Expected:** The plate shows up as failed somewhere the lab acts on. Its 37 samples land on `core.reassay_list`
  (AC-6.2: "samples go onto the re-assay list"), and the plate counts in the plate failure KPI.
- **Actual:** The file is logged in `assay.ingest_errors` and the run continues, which is good. But the plate has no
  `assay.plate_status` row, so `PLATE_FAIL_RATE` leaves it out. Its samples show up in `missing_results` as
  `NOT_ASSAYED` ("no assay run for this sample"), which is wrong because the samples were assayed and only the file
  was bad. None of them are on the re-assay list. The lab would have to work out for itself that 37 samples need
  re-running.
- **Fix hint:** Give an ingest-error plate a REJECTED status (for example `INGEST_ERROR`), or union the
  ingest-error samples into `reassay_list`, and use a distinct `missing_results.reason`.

## BUG-004: Truncating or re-hashing the tail of the audit chain goes undetected (Medium, gxp-validation-engineer)
- **FIXED 2026-10-30 (GxP seat):** every audited write appends a row to `audit.chain_checkpoint` (head seq + hash);
  `verify_chain` checks them (check `CHECKPOINT`). A forger who also rewrites the checkpoints is caught only by the
  external write-once anchor file (`integrity.write_chain_anchor`, `verify_chain(con, anchor=path)`, check `ANCHOR`),
  if `run.py` writes it (requested from DE). xfail marks removed; tests also in `tests/test_audit.py`.
- **Steps:** On any audited DB, delete the last N `audit.audit_log` rows, or edit the last row and recompute its
  `row_hash` with `compute_row_hash`. Then run `verify_chain`.
- **Expected:** The tampering is detected.
- **Actual:** `ChainResult(ok=True)`. A middle-row edit is caught correctly, even when the edited row is re-hashed
  (tests pass for the first, middle and last row edited without a re-hash). Only the tail is exposed, because nothing
  outside the chain records its length or last hash.
- **Note:** ADR 001 documents that a full-chain re-hash can't be detected. Tail truncation is a cheaper attack and is
  not listed. **Fix hint:** store an anchor (`rows_checked` plus the last `row_hash`) in `audit.chain_verify` or a
  file outside the DB after each run, and compare against it at the next verify. At minimum, add this to the known
  limitations in `docs/validation/`.

## BUG-005: A direct edit of a base table is undetected (Medium, gxp-validation-engineer)
- **FIXED 2026-10-30 (GxP seat):** `audit.reconcile` compares every live row of every audited table with its INSERT
  payload (now read back from the table, so types match). `verify_chain` reports it (check `RECORD`);
  `integrity.reconcile_records` writes `audit.record_reconciliation`, and `alcoa_findings` raises ALCOA-O2
  `RECORD_MISMATCH`. New planted problem INJ-11 (`generator.tamper.tamper_base_row`) needs DE/LIA wiring (HANDOFF).
- **Steps:** `UPDATE lims.custody_events SET performed_at = ...` (or any `lims.*` / `assay.*` row) by direct SQL, then
  run `verify_chain` and the dbt build.
- **Expected:** This is the most likely real-world tamper, so some check should notice it.
- **Actual:** Nothing notices it. The chain covers only `audit_log`, and the audit row's `new_value` JSON is never
  compared to the live base row. GXP-06 compares row counts only. INJ-7 tampers with the audit row, never the data.
- **Fix hint:** Add a reconciliation check: canonical_json(current base row) == the latest audit `new_value` for that key,
  with corrections applied. Write the result to `audit.*` and raise an ALCOA+ "Original/Accurate" finding.

## BUG-006: A duplicate or unknown plate file is silently ignored (Medium, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** a file whose name is not a planned plate in `lims.plate_runs` is still copied and hashed but not parsed, and is logged to `assay.ingest_errors`, naming any file with the same SHA-256 as a duplicate upload. xfail mark removed.
- **Steps:** Copy `PLATE-008.csv` to `PLATE-008 (1).csv` in `landing/plates/`, then build. This is the DUP case.
- **Expected:** The second upload is reported, either as an ingest error ("plate not in plate map" or "duplicate of
  PLATE-008, same SHA-256") or as a finding.
- **Actual:** The file is hashed into `lims.raw_files` and its 96 wells are written to `assay.well_reads`. It then drops
  out of `curve_fits`, `plate_status` and every report without any message. Results are not double-counted, which is
  good, but a reviewer has no way to see that a stray file was ever uploaded. Any file whose name isn't a planned
  plate gets the same silent treatment.

## BUG-007: An invalid `--seed` deletes the previous run's data before failing (Medium, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** `build()` and `main()` validate the seed (`check_seed`) before `_clean()`; the CLI prints a one-line argparse error. xfail mark removed.
- **Steps:** Run `.venv\Scripts\python -m pipeline.run --seed -1`.
- **Expected:** The bad argument is rejected up front and the existing `data/` is left alone.
- **Actual:** `build()` runs `_clean()` first and deletes `data/landing`, `data/raw` and the DuckDB file. Only then does
  `numpy.random.default_rng(-1)` raise `ValueError: expected non-negative integer` (raw traceback). **QA hit this for
  real** during probing and wiped the repo's `data/` folder. It was restored with a seed-42 rebuild, and
  `docs/results.json` was unchanged apart from the test counts.
- **Fix hint:** Validate `seed >= 0` in `main()` and `build()` before `_clean()`, and print a one-line error.

## BUG-008: Wrong row labels give the misleading error "got 8x12" (Low, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** separate messages for shape, row labels and column labels (e.g. `row labels must be A-H in order, got a,b,...`). xfail mark removed.
- **Steps:** Use a plate CSV with lowercase row labels (`a`..`h`) or a duplicated row label.
- **Expected:** The error names the actual problem, for example "row labels must be A-H, got a,b,...".
- **Actual:** `expected 8x12 grid A-H x 1-12, got 8x12`. The file is correctly rejected, but the message suggests the
  shape is fine and leaves the analyst guessing.

## BUG-009: Dependencies are unpinned and there is no README or Makefile (Medium, devops-engineer)
- **Steps:** Open `requirements.txt` and look for `README.md`.
- **Expected:** AC-12.3 wants dependencies pinned. AC-12.1 wants one documented command.
- **Actual:** `requirements.txt` lists bare package names, and neither `README.md` nor `Makefile` exists. This is
  OPS-01, which hasn't started yet, so it is logged here so it isn't forgotten. Parquet export works through DuckDB,
  but `pandas.read_parquet` fails because neither pyarrow nor fastparquet is installed. That's fine at runtime;
  just don't document `pd.read_parquet` in the README.

## BUG-010: Seat-level recall and answer-key tests skip INJ-11 (Low, analytics-engineer / LIA)
Logged 2026-10-30 by the Principal Engineer seat (flaw hunt, FLAW_HUNT FH-04c). Synthetic data only.
- **Steps:** In `generator/generate.py`, comment out the `problems.append(("INJ-11", ...))` call (lines 321-322), so
  INJ-11 is neither in the manifest nor planted. Run
  `pytest tests/test_generator.py tests/test_scorecard.py tests/test_alcoa.py tests/test_audit.py`.
- **Expected:** A test in LIA's scorecard file fails, because a required INJ type is gone.
- **Actual:** **69 passed in 28.59 s.** `tests/test_scorecard.py` uses `REQUIRED = INJ-1..8` for
  `test_every_required_inj_type_is_planted`, `test_recall_is_100pct_for_inj_1_to_8` and
  `test_caught_by_matches_hand_written_answer_key`, and `test_summary_counts_problems_not_keys` takes its required set
  from the planted manifest, so a missing type shrinks both sides. `tests/test_generator.py::test_every_required_inj_type_is_in_the_manifest`
  also hard-codes INJ-1..8. Only `tests/qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp` (6 seeds, about
  100 s) failed: 6 failed, 1 passed. The full suite would therefore still go red, so this is Low.
- **Fix hint:** set `REQUIRED = load_rules()["scorecard"]["required_inj_types"]`, add `"INJ-11": "RECORD_MISMATCH"`
  to `EXPECTED_CAUGHT_BY`, and add `integrity.alcoa_findings` RECORD_MISMATCH to the raw-flag union (it is already
  there). Read the generator test's list from config too. This is the INJ-11 recall test the GxP seat asked LIA for.
- **FIXED 2026-10-30 (LIA):** `tests/test_scorecard.py`:
  - `REQUIRED` now comes from config `scorecard.required_inj_types` (INJ-1..8, INJ-11).
  - `EXPECTED_CAUGHT_BY` has `INJ-11: RECORD_MISMATCH`, and a new test asserts the answer key covers every required type.
  - New fast test `test_inj11_record_edit_is_planted_and_caught`.
  - `test_summary_counts_problems_not_keys` asserts that planted required types equal the configured count.
  - Proof, on a scratch copy of the repo (the DE's file was not touched):
    - With the `problems.append(("INJ-11", ...))` lines commented out: **3 failed, 9 passed** (`test_every_required_inj_type_is_planted`, `test_inj11_record_edit_is_planted_and_caught`, `test_summary_counts_problems_not_keys`).
    - With INJ-11 planted but its expected flag changed to a non-existent code: **4 failed, 8 passed**.
  - Normal tree: 12 passed.
  - Not done: `tests/test_generator.py` still hard-codes INJ-1..8. That file is the DE's, so I asked them to read it from config.

## BUG-011: A landing CSV with a missing non-key column loads silently as NULLs (Medium, data-engineer)
- **FIXED 2026-10-30 (data-engineer):** `read_landing(..., expected=...)` compares each landing header with the table contract (lims.* via information_schema, plate_map, injected_problems) and raises `LandingSchemaError` naming the missing and unexpected columns. Second layer: `not_null` dbt tests on `stg_users.role`, `stg_subjects.group_name/site_id`, `stg_custody_events.sample_id/step/performed_at/recorded_at/location`.
Logged 2026-10-30 by the Principal Engineer seat (flaw hunt, FLAW_HUNT FH-03).
- **Steps:** `PYTHONPATH=. .venv/Scripts/python tools/schema_drift_probe.py` (works on a temp copy of
  `data/landing`).
- **Expected:** Any header that is not exactly the contract (DESIGN section 3) is rejected with a message.
- **Actual:** An extra column (`samples.csv` + `new_col`) and a renamed column (`custody_events.performed_by` ->
  `operator`) are rejected (`ValueError: columns [...] are not in lims.<table>`). A **dropped** column
  (`subjects.csv` without `site_id`) is ACCEPTED SILENTLY: the column loads as NULL for every subject and no dbt test
  checks `stg_subjects.site_id`. The same would happen to `custody_events.location` or `users.role`.
- **Fix hint:** in `pipeline/lims_load.read_landing`, compare the header with the table's column list and raise on
  any missing column. Add `not_null` dbt tests on the contract columns that must never be empty.

## BUG-012: `mart_lab_kpis` has no `PLATE_REJECT_INGEST_ERROR` row (Low, analytics-engineer / LIA)
Copied here from the HANDOFF "Open" lists (LIA and DE entries, 2026-10-30) so it is tracked.
- **Actual:** A plate rejected for `INGEST_ERROR` (BUG-003 fix) counts in `PLATE_FAIL_RATE` but has no per-reason row,
  so the per-reason rows no longer add up to the rejected total when an ingest error happens. Seed 42 has none.
- **Fix hint:** add the reason to the per-reason KPI list in `mart_lab_kpis.sql` and METRICS.md.
- **FIXED 2026-10-30 (LIA):** `INGEST_ERROR` added to the per-reason list in `mart_lab_kpis.sql` (row `PLATE_REJECT_INGEST_ERROR`, 0 on seed 42) and to METRICS.md. `test_kpis.py` recomputes it and asserts that every reject reason in `assay.plate_status` has its own KPI row.

---

## Observations (not bugs, no action required)
- **Re-run erases history.** Each `build()` deletes the previous DB, so the audit trail, chain-verify history and any
  earlier HASH_MISMATCH evidence go with it. That's fine for a reproducible demo, but in a real GCLP lab it would be
  record destruction. The validation pack's limitations should say so (gxp-validation-engineer).
- **Incremental re-ingest is impossible by design.** Calling `ingest_plates` twice on the same DB raises
  `AppendOnlyError` (atomic, no half-write). The only supported path is a full rebuild.
- **A single-well sample** (its duplicate well missing) gets `od_cv_pct = NaN`, so no DUP_CV flag fires and the
  result is reportable with no precision check. The spec says nothing about this case. Product-owner call.
- **Odd but valid seeds** (0, 1, 2, 3, 2^32-1, 10^12) all give 100% recall, FP 0.0% and dbt 131/131.
