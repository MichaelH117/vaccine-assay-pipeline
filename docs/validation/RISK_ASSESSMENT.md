# Risk Assessment (demo): vaccine-assay-pipeline

Owner: GxP Validation Engineer seat. Version 0.2 DRAFT, 2026-10-30 (after Tech Lead REVIEW F1/F5 and QA BUG-004/005).

> Portfolio demonstration on synthetic data. Not a validated system; no regulatory compliance is claimed.

## Method

A simplified GAMP 5 functional risk assessment. For each function:
- **Impact**: what happens to data integrity or to the reported result if it fails silently.
- **Likelihood of an undetected failure**, given the controls in place.
- **Rating**: High if a failure could change a reported result or hide a record change without anyone seeing it;
  Medium if a failure would produce a wrong or missing flag that a reviewer could still catch elsewhere; Low if the
  output is presentational or recomputed from validated data.
- CSA assurance level follows the rating (VALIDATION_PLAN.md section 2).

## Functions

| # | Function (code) | URS | Rating | Why | Controls | Assurance |
|---|---|---|---|---|---|---|
| F1 | Audited insert: `pipeline/audit.py::insert_records` | 01, 04, 05, 06 | **High** | Every LIMS and result record passes through it. A gap means a record with no who/what/when/why; an overwrite would replace data silently. | Batch insert + audit in one transaction; duplicate-key refusal; required performer and reason; table-name validation; cannot write the audit schema. | Scripted unit tests incl. negative and rollback tests; full-build coverage test (GXP-06). |
| F2 | No update/delete path: `audit.update`, `audit.delete`, `correct_record` | 02, 03 | **High** | If a change path existed, records could be altered without history. | The only change path appends a CORRECTION row with `supersedes_seq` and old/new values; base tables stay insert-only. | Unit tests: update/delete raise; correction chain points to the superseded row; base value unchanged. |
| F3 | Hash chain + `verify_chain` | 07, 30 | **High** | Detective control against direct SQL edits of the audit trail (DuckDB cannot block them, ADR 001). v0.1 missed tail truncation / tail re-hash (BUG-004). | SHA-256 chain over canonical JSON; gap-free sequence check; first broken row named; `audit.chain_checkpoint` row per audited write (CHECKPOINT check); optional external write-once anchor file (ANCHOR check). | Unit tests: clean OK, edit at row k -> k, deleted row, re-hashed forgery, tail truncation, rows appended outside the API, forger who rewrites checkpoints vs anchor; QA `test_qa_audit_chain.py`; INJ-7 on full build. |
| F3b | Record reconciliation: `audit.reconcile`, `integrity.reconcile_records`, `alcoa_findings` ALCOA-O2 | 29 | **High** | v0.1 protected only the audit_log. A direct `UPDATE` of a base row (e.g. re-attributing a custody event) changed the record with no trace (REVIEW F1, BUG-005): the most likely real fraud. | Audit INSERT payload is read back from the table after insert; every live row is compared with it; RECORD_MODIFIED / RECORD_DELETED / RECORD_UNAUDITED; RECORD check in `verify_chain`; RECORD_MISMATCH finding; planted INJ-11. | Unit tests (edit with field diff, delete, direct insert, duplicate key, corrections not flagged, tamper_base_row); QA `test_base_table_edit_detected`; full build clean (chain_verify ok on `clean_built`). |
| F4 | Tamper simulation: `generator/tamper.py` (INJ-7 audit row, INJ-11 base row) | 07, 29 | Medium | Test tool only. If it silently did nothing, INJ-7 would "pass" without proving anything. | Returns the changed audit_seq; raises if the event is absent; the test asserts the content actually changed. | Unit test tamper -> verify names the event. |
| F5 | Raw-file integrity: ingest copy + `integrity.rehash_raw_files` | 08, 09 | **High** | Raw plate data is the original record. An edited raw file would change every result on that plate. | Read-only copy, SHA-256 at ingestion, re-hash every run, missing file = mismatch, HASH_MISMATCH finding. | Unit tests: read-only enforced, edit and delete detected; full build all match. |
| F6 | ALCOA+ findings (`integrity.alcoa_findings`) | 10 | Medium | A missed finding hides a late or unattributable entry, but the underlying record and audit trail still exist for review. | Thresholds from config; one row per finding; dbt tests on keys and codes. | Fixture tests incl. 24h boundary; INJ-4 on full build. |
| F7 | Custody status and flags (`integrity.v_custody_status`, `custody_flags`) | 12-15 | Medium | A missed gap means a sample of unknown provenance could be reported; mitigated by the ALCOA Complete finding and reviewer custody view. | Config step order; first-occurrence order rule; dbt tests. | Fixture tests (gap, order, repeat-after-stored, freeze-thaw boundary); INJ-3 + clean build has 0 flags. |
| F8 | Ingestion + ID reconciliation (`ingest.py`) | 16, 17 | **High** | A swapped sample ID attaches a result to the wrong subject: a wrong reported value. | Well-level ID_MISMATCH vs custody `assayed` events; bad files logged, not crashed. | DE unit tests; INJ-2 scorecard. |
| F9 | 4PL fit and back-calculation (`curve.py`) | 18 | **High** | Directly produces the reported concentration. | Known-parameter recovery test; no extrapolation outside range; non-convergence -> FIT_FAIL. | DE unit tests (AC-5.2). |
| F10 | QC accept/reject (`qc.py`) | 19, 22 | **High** | A missed rejection lets a bad plate reach the report. | Versioned config thresholds stored on every flag; any plate flag -> REJECTED. | DE boundary tests per rule; INJ-1, 5, 6, 8 scorecard. |
| F11 | Reportable selection (`reportable.py`, `core.fct_reportable_result`, `missing_results`) | 20, 21 | **High** | Chooses which number is reported; double-counting or silent drops change the trial result. | Written through `insert_records` with a reason; dbt `unique` on sample_id; every sample in reportable XOR missing. | DE tests + test_outputs. |
| F12 | Immunogenicity stats (`stats.py`, `mart_immunogenicity`) | 23 | Medium | Wrong CI or GMFR pairing misstates efficacy, but it is recomputed from reportable results and checked by hand example. | Hand-calculated test, boundary tests. | LIA unit tests (AC-8.4). |
| F13 | Generator | 25 | Medium | Not GxP data, but non-reproducible data would make the evidence unrepeatable. | Seeded; SHA-256 identical twice. | DE test (AC-1.1). |
| F14 | KPIs, exports, charts, dashboard spec | 24, 27 | Low | Presentational, recomputed from validated tables. | Recompute test (AC-9.3). | Unscripted review + recompute test. |
| F15 | One-command run / environment | 28 | Low | Failure is loud (run stops). | Pinned deps, no network. | Smoke run. |

## Residual risks (accepted for the demo)

| Risk | Why accepted | What production would need |
|---|---|---|
| Direct SQL can change or delete rows (no triggers/REVOKE in DuckDB). | Detected, not prevented: hash chain (audit rows) + reconciliation (base rows); ADR 001. | Postgres triggers + REVOKE, or WORM storage. |
| A tamperer who edits a base row AND its audit payload AND re-hashes the chain AND rewrites the checkpoints passes every in-database check. | Caught only by the external anchor file, and only if it is written (`run.py`, requested from DE) and kept out of the tamperer's reach. The demo keeps it next to the DB file, which is rebuilt each run, so in the demo it protects one run only. | Signed anchors held by a separate system (or committed/sent off-machine) after every run. |
| Edits made after the anchor is written but before the next verify, to rows added after the anchor. | The anchor only vouches for rows up to its head_seq. | Anchor after every write batch, not only at the end of the run. |
| `performed_by` is supplied by code, not authenticated. | Out of scope (SPEC 6). | Real identity + e-signature (Part 11-style). |
| Audit timestamps come from the local clock. | Single laptop. | Trusted time source. |
| dbt-derived tables are rebuilt each run and not audited. | They are derivations of audited base tables (ADR 001). | Same; plus lineage and run logs retained. |
| QC thresholds are demo defaults. | UNVERIFIED vs ICH M10; versioned in config. | Method-specific validated acceptance criteria. |
