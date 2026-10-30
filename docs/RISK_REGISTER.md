# Risk register

Owner: Principal Engineer seat. Reviewed 2026-10-30. Scale: Likelihood and Impact are L / M / H.
"Owner" is the seat that would act. Status: **Open**, **Mitigated** (control in place, residual risk accepted), or
**Closed**. The GxP function-level risk assessment is in [validation/RISK_ASSESSMENT.md](validation/RISK_ASSESSMENT.md);
this register covers project and operating risk and links to it where they overlap. Synthetic data only.

| ID | Risk | L | I | Mitigation and evidence | Owner | Status |
|---|---|---|---|---|---|---|
| R-01 | A direct SQL edit of a LIMS or result record goes unnoticed (DuckDB has no triggers or REVOKE) | M | H | Record reconciliation, ALCOA-O2 RECORD_MISMATCH, planted INJ-11 ([ADR 007](team/adr/007-detect-record-edits-reconciliation-and-anchor.md)); FLAW_HUNT FH-04b shows the tests fail without it. Detection only, not prevention. | gxp-validation-engineer | Mitigated |
| R-02 | A forger who rewrites the row, its audit payload, the chain and the checkpoints passes every in-database check | L | H | External read-only anchor file. In the demo it sits next to the DB and is rebuilt each run, so it protects one run only. Production: signed anchor held by another system. | gxp-validation-engineer | Open (accepted for demo) |
| R-03 | A re-run deletes the previous audit trail | H (every run) | H in a real lab, L in the demo | Documented (KNOWN_ISSUES KI-01). Production needs incremental, append-only loads and no `_clean()`. | data-engineer | Open (accepted for demo) |
| R-04 | A killed or crashed run leaves `data/` half built while `docs/results.json` shows the last good run | M (happened once, low memory) | M | None yet. Fix: build in a temp folder, swap on success, write results.json last (FLAW_HUNT FH-09). | data-engineer | Open |
| R-05 | Landing schema drift: a dropped column loads as NULLs | M | M | Extra and renamed columns are already rejected. Dropped column logged as BUG-011. | data-engineer | Open |
| R-06 | QC thresholds (R² 0.98, recovery 80-120%, CV 20%, OD range 0-4.5) are demo defaults, not checked against ICH M10 | H | M | All in versioned `config/qc_rules.yaml`, stamped on every flag (`rule_version`); SPEC marks them UNVERIFIED. | tech-lead | Open (accepted for demo) |
| R-07 | Recall is gamed by moving a planted type from "required" to "optional", or by changing the answer key to fit | L | M | Hand-written answer key in tests; optional count printed in the headline; FP rates shown next to recall; the one FP left visible (FLAW_HUNT FH-05). Gap: BUG-010. | analytics-engineer | Mitigated |
| R-08 | Test harness drifts from the real pipeline, so tests describe a different system | M | H | `pipeline.run.integrity_step` shared by `build()` and `staged_build` ([postmortem](POSTMORTEM_2026-10-30_INJ11_harness_drift.md)). | qa-engineer | Mitigated |
| R-09 | Unpinned dependencies: a new dbt or DuckDB release changes results or breaks the build | M | M | BUG-009, handed to devops-engineer (pins, CI). | devops-engineer | Open |
| R-10 | Low memory on the build PC kills runs and hides failures for a round | H | L | One heavy process at a time (TEAM rules). Build-only run is 10.6-12.3 s; the full `--test` run (about 3.5 to 4 min) is the heavy one. | engineering manager | Mitigated |
| R-11 | A reader takes the synthetic results (GMT, seroresponse) as real vaccine data | L | H | "Synthetic" on every chart title, the README, results.json source and this brief. | principal-engineer | Mitigated |
| R-12 | Superlinear steps (reportable selection, audited writes) make a 100x study slow | M at 100x | M | Measured: 100x builds in 528.2 s, reportable selection 221.1 s of it (SCALE_AND_COST.md). Fix path listed there. | data-engineer | Open |
| R-13 | `performed_by` comes from code, not an authenticated user | H | H in production | Out of scope (SPEC section 6); listed as a residual risk in the validation pack. | gxp-validation-engineer | Open (accepted for demo) |
| R-14 | Single-well samples (duplicate well missing) are reported with no precision check | L | M | Logged as an observation in BUGS.md, product call pending (KNOWN_ISSUES KI-07). | product-owner | Open |
