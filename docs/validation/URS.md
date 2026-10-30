# User Requirements Specification (demo): vaccine-assay-pipeline

Owner: GxP Validation Engineer seat. Version 0.2 DRAFT, 2026-10-30 (adds URS-29, URS-30 after REVIEW F1/F5, BUG-004/005). Source: docs/team/SPEC.md (US-1 to US-12).

> Demonstration on synthetic data. Not a validated system; no regulatory compliance is claimed.

Each requirement has an ID (`URS-nn`), the SPEC story / acceptance criteria it comes from, and a risk rating from
[RISK_ASSESSMENT.md](RISK_ASSESSMENT.md). "Shall" statements are testable; the test that proves each one is in
[TRACEABILITY.md](TRACEABILITY.md).

## A. Data integrity and audit trail (US-3)

| ID | Requirement | Source | Risk |
|---|---|---|---|
| URS-01 | Every record inserted into a LIMS or assay result table shall produce an audit row recording who (performed_by), what (table, record key, field, old value, new value), when (UTC timestamp) and why (reason). | AC-3.1 | H |
| URS-02 | The write API shall have no update or delete path for audited records; an attempt shall raise an error. | AC-3.2 | H |
| URS-03 | A correction shall be stored as a new audit row that points to the row it supersedes; the original value shall stay readable. | AC-3.2 | H |
| URS-04 | Inserting a record whose key already exists shall be refused (no silent overwrite). | AC-3.2 (derived) | H |
| URS-05 | A record insert and its audit rows shall be written in one transaction: both or neither. | AC-3.1 (derived) | H |
| URS-06 | An insert without a performer or a reason shall be refused. | AC-3.1, ALCOA Attributable (derived) | H |
| URS-07 | Each audit row shall carry a SHA-256 hash of the previous row's hash plus its own content; a verify function shall return OK on an untouched trail and name the first broken row (sequence, table, record key) after a direct edit. | AC-3.3, INJ-7 | H |
| URS-08 | Raw plate CSVs shall be copied to a read-only area at ingestion with their SHA-256 stored; processing shall never modify them. | AC-3.5 | H |
| URS-09 | A re-hash of each raw file shall be compared with the stored hash; a mismatch or a missing file shall be reported as an Original finding (HASH_MISMATCH). | AC-3.4 | H |
| URS-29 | Every live row of an audited table shall be reconciled with its INSERT audit payload; a modified, deleted, or unaudited row shall be reported (verify result and an ALCOA+ Original finding RECORD_MISMATCH). | AC-3.3, AC-3.4 (derived), REVIEW F1, BUG-005, INJ-11 | H |
| URS-30 | Deleting or re-hashing the newest audit rows shall be detected: by in-database checkpoints, and, against a forger who also rewrites those, by a write-once anchor file kept outside the database. | AC-3.3 (derived), REVIEW F5, BUG-004 | H |
| URS-10 | ALCOA+ findings shall be written one row per finding with rule_id, attribute and key, covering at least: Attributable (null or unknown performer), Contemporaneous (entry recorded more than the configured hours after performance, LATE_ENTRY), Original (HASH_MISMATCH, RECORD_MISMATCH), Complete (CUSTODY_GAP). | AC-3.4, INJ-4 | M |

## B. Chain of custody (US-2)

| ID | Requirement | Source | Risk |
|---|---|---|---|
| URS-11 | The LIMS shall hold samples, aliquots and custody events with event_id, sample_id, step, performed_by, performed_at, recorded_at, location and reason. | AC-2.1 | M |
| URS-12 | A custody status per sample shall show the current step and whether custody is complete, using the configured step order. | AC-2.2 | M |
| URS-13 | A skipped custody step shall be flagged CUSTODY_GAP, naming the missing step. | AC-2.3, INJ-3 | M |
| URS-14 | A step performed before an earlier step shall be flagged CUSTODY_ORDER (first occurrence of each step only, so repeat assays are not false alarms). | AC-2.4, DESIGN R8 | M |
| URS-15 | An aliquot over the configured freeze-thaw limit shall be flagged FREEZE_THAW_EXCEEDED. | AC-2.5 | M |

## C. Assay processing and reporting (US-4 to US-7)

| ID | Requirement | Source | Risk |
|---|---|---|---|
| URS-16 | A malformed plate file shall be rejected and logged without stopping the run. | AC-4.1 | M |
| URS-17 | A plate-map sample that does not match the LIMS assay record shall be flagged ID_MISMATCH. | AC-4.4, INJ-2 | H |
| URS-18 | Concentrations shall be back-calculated from a per-plate 4PL fit; signals outside the working range shall be labelled `<LLOQ` / `>ULOQ` and not extrapolated. | AC-5.1 to 5.5 | H |
| URS-19 | Plate QC rules (FIT_FAIL, STD_RECOVERY, CTRL_OOR, BLANK_HIGH) shall reject a plate; sample rules (DUP_CV, ABOVE_ULOQ, ID_MISMATCH) shall block a result. Each flag shall store the rule version, measured value and threshold. | AC-6.1 to 6.5 | H |
| URS-20 | Exactly one reportable result per sample shall be selected, from an accepted plate with no blocking flag (latest valid run), and the choice shall be audited with a reason. | AC-7.1, 7.2 | H |
| URS-21 | Samples with no valid result shall be listed with a reason, never dropped. | AC-7.4 | H |
| URS-22 | All QC thresholds shall come from one versioned config file. | SPEC 4, ADR 005 | M |

## D. Analysis, reporting and operation (US-1, US-8 to US-12)

| ID | Requirement | Source | Risk |
|---|---|---|---|
| URS-23 | GMT, GMFR and seroresponse with CIs shall be computed by group and visit as defined in METRICS.md. | AC-8.1 to 8.5 | M |
| URS-24 | Lab KPIs shall match an independent recompute from base tables. | AC-9.1 to 9.3 | L |
| URS-25 | The generator shall be reproducible (same seed, byte-identical files) and contain synthetic identifiers only. | AC-1.1, 1.5 | M |
| URS-26 | A detection scorecard shall show every planted problem as detected (100% recall INJ-1 to INJ-8). | AC-10.1, 10.2 | M |
| URS-27 | Marts shall be exported for Power BI and 3 PNG charts rendered. | AC-11.3, 11.4 | L |
| URS-28 | One command shall rebuild everything and run the tests; dependencies pinned, no network at runtime. | AC-12.1 to 12.3 | L |
