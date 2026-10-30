# ADR 007: Detect record edits by reconciling base rows to the audit trail, plus an external chain anchor

Status: Accepted 2026-10-30. **Supersedes the "Detective (hash chain)" part of ADR 001.** ADR 001's choice of DuckDB
and the preventive write API still stand. Written by the Principal Engineer seat from the fix-round record
(REVIEW.md F1/F5, BUGS.md BUG-004/005, HANDOFF.md 2026-10-30 GxP and DE entries), so the reversal has its own record.

## Context
ADR 001 said tamper detection was "a hash chain over `audit.audit_log`; INJ-7 proves it". Review and QA found that
this claim covered the wrong object:
- **F1 / BUG-005 (High):** `UPDATE lims.custody_events SET ...` by direct SQL left the chain OK. The chain protects the
  audit rows, not the records they describe. A real fraud edits the record.
- **F5 / BUG-004 (Medium):** deleting the newest audit rows, or editing the last row and re-hashing it, left a valid
  shorter chain. Nothing outside the chain remembered its length or head hash.

## Options
1. Keep ADR 001 and list both gaps as known limitations. Cheapest, but the project's main GxP claim would be false.
2. **Reconcile every live base row with its INSERT audit payload, add in-database checkpoints, and write a read-only
   anchor file outside the database.** Pure Python and SQL, no new dependency.
3. Move to PostgreSQL with triggers and `REVOKE UPDATE, DELETE`. This prevents the edit, not just detects it, but
   it needs a server and credentials, and it breaks the one-command laptop run (ADR 001's reason for DuckDB).

## Choice
Option 2.
- `audit.insert_records` stores the row as read back from the table, so types match later (VALIDATION_SUMMARY DV-05).
- `audit.reconcile` reports RECORD_MODIFIED (with a field diff), RECORD_DELETED and RECORD_UNAUDITED.
  `verify_chain` runs it as check `RECORD`; `integrity.reconcile_records` writes `audit.record_reconciliation`;
  `alcoa_findings` raises ALCOA-O2 `RECORD_MISMATCH`.
- Every audited write appends to `audit.chain_checkpoint` (check `CHECKPOINT`).
- `integrity.write_chain_anchor` writes `data/warehouse/audit_anchor.json` (head seq + head hash), read-only
  (check `ANCHOR`).
- New planted problem INJ-11 (`generator/tamper.py::tamper_base_row`) edits one base row and leaves the audit trail
  alone, so only reconciliation can catch it. It is a required type in the scorecard.

## Consequences
- Seed 42: INJ-11 (EVT-000655) is caught by RECORD_MISMATCH. INJ-7 is now caught twice: by the chain
  (AUDIT_CHAIN_BROKEN) and by reconciliation, because its tampered audit payload no longer matches the base row. The
  second catch is on SMP-00180, which is the one "unexplained" sample flag in the false-positive rate (1 of 360). We
  did not add RECORD_MISMATCH to INJ-7's expected flags just to reach 0%; see FLAW_HUNT FH-05.
- Still detection, not prevention. A forger who rewrites the base row, its payload, the chain and the checkpoints is
  caught only by the anchor, and only while the anchor is out of their reach. In the demo the anchor sits next to the
  DB and is rebuilt every run (RISK_REGISTER R-02).
- The anchor head is not copied into `docs/results.json`, because it covers run-clock timestamps and would make
  results.json differ between identical runs (HANDOFF DE entry). This reverses REVIEW F5's suggestion.
- Evidence: `tests/test_audit.py::test_base_row_edit_is_found_with_field_diff`, `::test_tail_truncation_caught_by_checkpoint`,
  `::test_forger_who_rewrites_checkpoints_is_caught_only_by_external_anchor`,
  `tests/qa/test_qa_audit_chain.py::test_base_table_edit_detected`. FLAW_HUNT FH-04 shows the reconciliation tests fail
  when the check is removed.
