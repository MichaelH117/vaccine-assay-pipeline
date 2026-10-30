# ADR 001: DuckDB, with append-only enforced by the write API and a hash chain

Status: Accepted 2026-10-29 (decision D1, Engineering Manager; Michael may override). Covers US-2, US-3.
**Partly superseded 2026-10-30 by [ADR 007](007-detect-record-edits-reconciliation-and-anchor.md):** the "Detective (hash chain)" control below did not cover base-table edits or tail truncation. The DuckDB choice and the preventive write API still stand.

## Context
The mini-LIMS needs tables for samples, aliquots, custody events and results, plus an audit trail that cannot be
changed silently (AC-3.1 to AC-3.3). Michael's other projects use DuckDB with dbt-duckdb on Windows, with no server.

## Options
1. **DuckDB.** No setup, one file, dbt-duckdb already proven in clinical-data-review. But DuckDB has no triggers, no
   users and no GRANT/REVOKE, so the database itself cannot block an UPDATE on `audit_log`.
2. **PostgreSQL.** Real `BEFORE UPDATE OR DELETE` triggers and `REVOKE UPDATE, DELETE` make append-only a database
   rule. It is closer to a real LIMS backend. But it needs a server on Windows, credentials, and a harder one-command run.
3. DuckDB now, Postgres later behind a thin adapter. This adds an abstraction layer that we do not need yet.

## Choice
Option 1. Append-only is enforced in two layers:
- **Preventive (API):** all writes go through `pipeline/audit.py`. It offers `insert_records` and `correct_record`
  only. `update` and `delete` exist only to raise `AppendOnlyError` (AC-3.2).
- **Detective (hash chain):** every audit row stores `prev_hash` and `row_hash`. `verify_chain` names the first
  broken row. INJ-7 edits a row with direct SQL to prove that tampering is caught (AC-3.3).

## Consequences
- Anyone with the DuckDB file can still change rows directly. The chain detects the change but does not prevent it.
  The validation pack must say this, as a known limitation of the demo.
- dbt models are derived and rebuilt every run, so they are not audited. Only the Python-written base tables
  (`lims.*`, `assay.*`) are audited.
- A Postgres port later means adding triggers and REVOKE. The table contracts in DESIGN.md do not change.

## Amendment 2026-10-29 (TL, after build)
- Pipeline writes are audited as `performed_by = 'SYS-PIPELINE'`, a system account that is not in `lims.users`.
- `audit.file_integrity` gains `checked_at`. Integrity check tables (`chain_verify`, `file_integrity`) are written
  directly, not through `insert_records`: they hold check results, not GxP records.
- Known gap found in review (REVIEW.md F1): the hash chain covers `audit.audit_log` only. A direct UPDATE of a base
  table row (for example `lims.custody_events.performed_at`) is not detected yet. A base-table vs audit reconciliation
  is the planned fix; until then the validation pack must say so.
