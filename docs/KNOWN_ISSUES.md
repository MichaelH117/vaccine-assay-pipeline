# Known issues and limits

Owner: Principal Engineer seat, 2026-10-30. Honest limits of the demo, and what would fix each one. Open defects
with a reproducer are in [team/BUGS.md](team/BUGS.md); risks with owners are in [RISK_REGISTER.md](RISK_REGISTER.md).
All data is synthetic.

| ID | Limit | Why it is like this | What would fix it |
|---|---|---|---|
| KI-01 | **Every run rebuilds from nothing and deletes the previous audit trail.** There is no incremental load; a second `ingest_plates` on the same DB raises `AppendOnlyError`. | A seeded, reproducible demo is worth more here than history. In a GCLP lab this would be record destruction. | Keep the DB between runs; load only new files (keyed by SHA-256, which is already stored); never call `_clean()` in production mode. |
| KI-02 | **A killed run leaves `data/` half built,** while `docs/results.json` still describes the previous run (FLAW_HUNT FH-09). | `build()` deletes first and builds in place. | Build into `data.tmp/`, rename on success, write results.json last. |
| KI-03 | **Tamper detection, not prevention.** Anyone with the DuckDB file can edit rows; reconciliation, the hash chain and checkpoints catch it. The anchor file sits next to the DB, so it protects one run only. | DuckDB has no triggers, users or REVOKE (ADR 001, ADR 007). | PostgreSQL with triggers and `REVOKE UPDATE, DELETE`, or WORM storage; signed anchors held by a separate system. |
| KI-04 | **No authentication or e-signature.** `performed_by` is a value the code supplies. | Out of scope (SPEC section 6). | Real identity provider plus Part 11-style signing on release. |
| KI-05 | **Lab timestamps have no time zone.** A 24 h LATE_ENTRY limit spanning a daylight-saving change can be off by an hour (FLAW_HUNT FH-07). Audit times are UTC. | The landing contract never named a zone; the generator emits no DST. | Store lab times as UTC with the site's zone in the contract; compute durations in UTC. |
| KI-06 | **A dropped column in a landing CSV loads as NULLs** (BUG-011). | The loader checks for unknown columns, not missing ones. | Exact header check in `lims_load.read_landing`, plus `not_null` dbt tests. |
| KI-07 | **A single-well sample has no precision check** (CV is NaN, so DUP_CV cannot fire). | The spec is silent; product call pending. | Rule: a sample needs 2 valid wells, or it goes on the re-assay list. |
| KI-08 | **QC thresholds are demo defaults,** not checked against ICH M10 or a method validation report. | No real method exists. | Method-specific acceptance criteria from validation, kept in the versioned config. |
| KI-09 | **One synthetic ELISA, one analyte, one lab.** No neutralization titers, no multiplex, no robot or reader integration. | Scope (ADR 002). | Add assay types behind the same plate contract. |
| KI-10 | **Turnaround time reflects the generator's scheduling** (plates run 7 days after the last sample is aliquoted), not a real lab's queue. Median 12.39 days, P90 15.95 days. | Synthetic schedule. | Real reader and LIMS timestamps. |
| KI-11 | **The false-positive rate is 0.277%, not 0%.** SMP-00180 gets RECORD_MISMATCH as a side effect of INJ-7 (ADR 007). | Left visible on purpose (FLAW_HUNT FH-05). | Nothing to fix; a reviewer can trace it. |
| KI-12 | **A 100x study (36,000 samples) takes 528.2 s on a laptop,** 221.1 s of it in reportable selection (SCALE_AND_COST.md). | Selection filters all runs once per sample (quadratic); audited writes hash serially. | Batch audit hashing; set-based reportable selection in SQL. |
| KI-13 | **Unpinned dependencies, no CI yet** (BUG-009). | DevOps seat runs after this pass. | Pinned `requirements.txt`, GitHub Actions, quickstart. |
| KI-14 | **The INJ-11 recall check exists only in the slow seed sweep** (BUG-010). | The fast tests kept the old INJ-1..8 list. | Read the required list from config and add INJ-11 to the answer key. |
| KI-15 | **The validation pack is DRAFT v0.2;** the summary has not been concluded (GXP-07). | Waiting for the final QA re-test. | GxP seat completes VALIDATION_SUMMARY with the final run's evidence. |
