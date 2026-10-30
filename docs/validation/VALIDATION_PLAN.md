# Validation Plan (demo): vaccine-assay-pipeline

Owner: GxP Validation Engineer / Data Integrity Lead seat. Version 0.1 DRAFT, 2026-10-29.

> **This is a portfolio demonstration of GxP validation practice, not a validated system.** It runs on synthetic data
> only. No claim of compliance with 21 CFR Part 11, EU Annex 11, GCLP, or any other regulation is made or implied.
> The plan shows how the work *would* be approached under GAMP 5 (2nd ed.) and the FDA Computer Software Assurance
> (CSA) guidance, scaled down to a one-person demo.

## 1. Purpose and scope

The system turns synthetic plate-reader CSVs and mini-LIMS records into reportable ELISA IgG concentrations and
immunogenicity summaries (SPEC US-1 to US-12). This plan covers the functions that create, change, or protect GxP-like
records:

| In scope | Out of scope (SPEC section 6) |
|---|---|
| Mini-LIMS load and chain of custody (US-2) | Real LIMS products, instrument drivers, robots |
| Append-only audit trail, hash chain, ALCOA+ checks (US-3) | e-signatures, login/authentication, role permissions |
| Raw-file ingestion, 4PL fit, QC, reportable selection (US-4 to US-7) | Assay method validation (precision, parallelism...) |
| Immunogenicity stats, KPIs, scorecard (US-8 to US-10) | Infrastructure qualification (it is a laptop) |

## 2. System category and approach

- **GAMP 5 category:** treated as **Category 5 (custom application)** built on Category 1 infrastructure (Python,
  DuckDB, dbt-duckdb). Every line of pipeline logic is bespoke, so it gets the most scrutiny.
- **CSA approach:** effort follows risk to data integrity and to the reported result, not a fixed IQ/OQ/PQ script set.
  - **High risk** functions (audit trail, raw-file integrity, reportable result selection, QC accept/reject, 4PL
    back-calculation): scripted, automated tests with explicit pass criteria, including negative tests (tamper,
    overwrite, missing who/why) and boundary tests.
  - **Medium risk** (custody flags, ALCOA+ findings, immunogenicity stats): automated tests on fixtures plus the
    full-build detection scorecard.
  - **Low risk** (charts, exports, dashboard spec): unscripted / exploratory checks and the existing smoke run.
- **Evidence** is the automated test output (pytest, `dbt test`) captured in HANDOFF.md and in TRACEABILITY.md. CSA
  favours this over screenshots.

Risk ratings and reasons: [RISK_ASSESSMENT.md](RISK_ASSESSMENT.md).

## 3. Deliverables

| Document | Status | Content |
|---|---|---|
| VALIDATION_PLAN.md (this) | DRAFT 0.1 | approach, roles, acceptance |
| [URS.md](URS.md) | DRAFT 0.1 | user requirements, each traced to SPEC story / AC IDs |
| [RISK_ASSESSMENT.md](RISK_ASSESSMENT.md) | DRAFT 0.1 | per-function data-integrity risk (H/M/L) and the controls |
| [ALCOA_CHECKLIST.md](ALCOA_CHECKLIST.md) | DRAFT 0.1 | ALCOA+ control matrix with evidence (file and test names) |
| [TRACEABILITY.md](TRACEABILITY.md) | DRAFT (final in Phase 2, GXP-07, after QA-02) | URS -> design -> test -> result |
| [VALIDATION_SUMMARY.md](VALIDATION_SUMMARY.md) | DRAFT (final in Phase 2, GXP-07) | what was tested, results, deviations, limitations |

## 4. Roles (team seats, see dev-team/TEAM.md)

| Role | Seat | Responsibility here |
|---|---|---|
| System owner / process owner | Product Owner (Michael approves) | approves URS and the final summary |
| Validation lead | GxP Validation Engineer | plan, URS, risk, traceability, ALCOA+ controls, audit-trail code |
| Developers | Data Engineer, Lab Informatics Analyst | build to DESIGN.md, unit tests |
| Independent tester | QA Engineer | TEST_PLAN.md, edge tests, defects in BUGS.md |
| Technical reviewer | Tech Lead | code review (TL-01), approves design changes |

Independence: the QA seat tests work it did not write. In a real system a separate QA unit would approve. Here
the "approval" is Michael's review, which is recorded, not signed.

## 5. Acceptance criteria for the demo

1. Every **High** risk URS item traces to at least one automated test that passes on the final build.
2. Detection scorecard recall is 100% for INJ-1 to INJ-8 on seed 42 (AC-10.2).
3. The audit chain verifies OK on a clean build and fails at exactly the INJ-7 record on the injected build.
4. Every ALCOA+ attribute in ALCOA_CHECKLIST.md names a control and at least one evidence file or test.
5. Every deviation (failed test, skipped test, workaround) is written in VALIDATION_SUMMARY.md, not hidden.

## 6. Change control

- QC thresholds live in `config/qc_rules.yaml` with a `version` string stamped on every QC flag; a change goes
  through a Tech-Lead-reviewed change (DESIGN 5).
- Contract changes (tables, signatures) need a DESIGN.md update approved by the Tech Lead.
- Git history is the change record. The seat commits only when the Engineering Manager asks; Michael pushes.

## 7. Known limitations accepted up front

- **Append-only is enforced by the API, not the database** (ADR 001, DESIGN R1). DuckDB has no triggers, users, or
  REVOKE. Direct SQL can still change rows. Detective controls only: the SHA-256 hash chain and checkpoints catch
  edits to the audit trail (INJ-7), and record reconciliation catches edits to the base tables (INJ-11, added
  2026-10-30 after REVIEW F1). A forger who rewrites base row, audit row, chain and checkpoints together is caught only
  by the external anchor file. A production port would add Postgres triggers + REVOKE, or a WORM store.
- No user authentication: `performed_by` is a synthetic user ID passed by the code, not a logged-in identity.
- The database is rebuilt on every run. "Enduring" and "Available" are demonstrated within a run and by
  reproducibility from seed, not by backup/archival.
- QC thresholds are demo defaults, UNVERIFIED against ICH M10.
