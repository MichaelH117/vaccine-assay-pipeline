# Validation Summary (demo): DRAFT

Owner: GxP Validation Engineer seat. Version 0.2 **DRAFT**, 2026-10-30. To be completed in Phase 2 (GXP-07) after
QA-02, with the real pytest and `dbt test` output.

## Statement of status

**This project is a portfolio demonstration of GxP validation and data-integrity practices. It is NOT a validated
system and makes no claim of compliance with 21 CFR Part 11, EU GMP Annex 11, GCLP, or any other regulation.** All
data is synthetic. The documents in this folder show how a GAMP 5 / CSA risk-based approach would be applied, scaled to
a one-person demo.

## What has been tested so far (Phase 0/1, GxP seat only)

| Area | How | Result (2026-10-29) |
|---|---|---|
| Audit write API (`pipeline/audit.py`) | Scripted pytest on in-memory DuckDB, incl. negative, rollback and tamper tests | `tests/test_audit.py`: 26 passed, 3 skipped (build tests) |
| Custody models (`dbt/models/integrity/`) | SQL rendered with the real config vars and run on hand-made staging fixtures | `tests/test_custody.py`: 6 passed, 3 skipped |
| ALCOA+ findings + raw-file re-hash | Same, plus real files on a tmp dir | `tests/test_alcoa.py`: 5 passed, 2 skipped |

Combined run: `.venv\Scripts\python -m pytest tests/test_audit.py tests/test_custody.py tests/test_alcoa.py` gave
**37 passed, 8 skipped**. The 8 skips are full-build tests waiting for the `built` / `clean_built` fixtures (DE-09).

## Not yet tested (to be filled at GXP-07)

- Full build: GXP-06 audit coverage, INJ-3, INJ-4, INJ-7 on real data, clean-build zero custody flags.
- `dbt test` on the integrity models (the models have not yet been run by dbt itself, only through the Jinja test shim,
  because DE-08 staging models do not exist yet).
- Other seats' high-risk functions (ingestion, 4PL, QC, reportable selection).

## Deviations (so far)

| # | Deviation | Impact | Action |
|---|---|---|---|
| DV-01 | Integrity models tested through a Jinja shim, not through `dbt build`. | The SQL logic is tested; dbt wiring (ref names, vars, schema) is not yet. | Re-run under `dbt build` once staging exists; full-build tests cover it. |
| DV-03 | Tech Lead review F1 / QA BUG-005: a direct edit of a base table was not detected. The v0.1 claim "the hash chain detects direct SQL edits" covered only the audit_log. | High: the most realistic fraud was invisible. | Fixed 2026-10-30: record reconciliation (URS-29), ALCOA-O2 RECORD_MISMATCH, planted INJ-11. Scorecard wiring pending DE/LIA. |
| DV-04 | QA BUG-004: deleting or re-hashing the newest audit rows was not detected. | Medium. | Fixed 2026-10-30: in-DB checkpoints + optional external anchor (URS-30). Residual risk kept and documented (RISK_ASSESSMENT). |
| DV-05 | Audit INSERT payload changed from "the DataFrame as given" to "the row as stored" (read back after insert). | Needed for reconciliation; same contract columns. | Noted for TL review. |
| DV-02 | Added column `checked_at` to `audit.file_integrity` (not in DESIGN 3.2). | Additive; lets `alcoa_findings` use the latest check per file. | Tech Lead to confirm in TL-01. |

## Known limitations

See VALIDATION_PLAN.md section 7 and RISK_ASSESSMENT.md "Residual risks". The key one: append-only is enforced by the
API only; the database cannot block direct SQL edits. The hash chain + checkpoints (audit rows, INJ-7) and record
reconciliation (base rows, INJ-11) detect such edits but do not prevent them. A tamperer with full database access
who rewrites the base row, its audit payload, the chain and the checkpoints is caught only by the external anchor
file, and only while that file is out of their reach.

Note (2026-10-30): the GxP seat's own tests now run the full-build checks too (`built` fixtures exist): see the
HANDOFF entry for the current counts. The tables above are the 2026-10-29 Phase 1 snapshot.

## Conclusion

Not concluded. DRAFT pending Phase 2.
