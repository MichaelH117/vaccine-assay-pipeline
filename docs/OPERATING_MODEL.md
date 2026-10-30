# Operating model: how a real lab data team would run this

Owner: Principal Engineer seat, 2026-10-30. **This is a proposal for a hypothetical deployment.** The project has
never been deployed, has no users and no on-call rota. It describes how the controls already in the code would be
owned and run, so a reviewer can judge whether they would hold up in a GCLP lab. All data is synthetic.

## Roles (RACI for the main activities)
R = does it, A = accountable, C = consulted, I = informed.

| Activity | Assay lab data reviewer | Lab data engineer | Data integrity / QA | Study statistician | Lab manager |
|---|---|---|---|---|---|
| Daily run and plate release | R | C | I | I | A |
| Re-assay list to the bench | R | I | I | I | A |
| QC rule or threshold change (`config/qc_rules.yaml`) | C | R | A (approves) | C | C |
| Pipeline code change | I | R | C (GxP impact) | I | A |
| Audit-trail review, reconciliation findings | C | C | R / A | I | I |
| Immunogenicity tables to the trial | C | I | I | R | A |
| Incident (failed run, RECORD_MISMATCH, chain break) | C | R | A for integrity findings | I | I |

In this repo the same functions are seats: product-owner, tech-lead, data-engineer, Lab Informatics Analyst,
qa-engineer, gxp-validation-engineer, devops-engineer, principal-engineer. [team/HANDOFF.md](team/HANDOFF.md) logs
who did what.

## Service levels (proposed)
| What | Target | Measured today (seed 42, synthetic) |
|---|---|---|
| Plate results reviewed after the reader export lands | same working day | build-only run 10.6-12.3 s for 13 plates |
| Turnaround, sample received to reportable result | median ≤ 14 days, P90 ≤ 21 days (a lab target, to be agreed) | median 12.39 days, P90 15.95 days (generator's schedule, KI-10) |
| Integrity findings (RECORD_MISMATCH, AUDIT_CHAIN_BROKEN) triaged | within 1 working day; release blocked until closed | seed 42 plants both on purpose; both are caught |
| Pipeline availability | business hours; a failed run is re-run the same day | n/a |
| Unexplained-flag rate | ≤ 5% of samples, alert above | 0.277% (1 of 360) |

## On-call and runbook (business hours, one primary, one backup)
| Signal | First action | Escalate to |
|---|---|---|
| Run stops with an error | Read the step number it printed (1/8 to 8/8); re-run once; if it fails again, open an incident and do not release | Lab data engineer |
| A plate in `assay.ingest_errors` | Check the file against the reader export; re-export; the plate's samples are already on the re-assay list | Reviewer |
| `chain_ok = false` or ALCOA-O2 RECORD_MISMATCH that is not a planted test | Freeze releases; keep the DB file and anchor; compare `audit.record_reconciliation` detail (field: audit value -> live value) | Data integrity / QA, same day |
| Unexplained-flag rate above 5%, or any plate rejected with no clear cause | Hold release; check whether a reagent lot or the reader changed | Lab manager |
| dbt test failure | The build stops; nothing is exported. Fix the model or the data, re-run | Lab data engineer |

## Change control
- Every QC threshold lives in `config/qc_rules.yaml`, and every flag stores the `rule_version` it ran under. A
  threshold change needs a version bump, QA approval, and a re-run of the scorecard (13 of 13, FP rates) before release.
- Code changes go through review by a second engineer (REVIEW.md is the model) and the full suite
  (`python -m pipeline.run --test`: pytest plus dbt) before merge. Proposed CI is the devops seat's next task.
- A bug fix lands with its test switched on: open bugs carry an `xfail(strict=True)` test, so a fix cannot merge
  without enabling it (BUGS.md).
- **Test helpers may wrap pipeline steps but must not re-implement them** (lesson from the
  [postmortem](POSTMORTEM_2026-10-30_INJ11_harness_drift.md)).
- Validated-state changes follow the validation pack ([validation/VALIDATION_PLAN.md](validation/VALIDATION_PLAN.md)):
  a risk-based re-test of the affected functions.

## Data ownership
- **Data owner:** the lab manager (results) and the trial sponsor (subject data).
- **Data steward:** the assay lab data reviewer.
- **Subject identity:** coded IDs only (`SUBJ-xxxx`); the key linking codes to people stays at the clinical site
  and never enters this system (FLAW_HUNT FH-06).
- **Retention:** in production the DB and audit trail are kept for the trial's retention period; the demo's
  rebuild-every-run behaviour (KI-01) would be switched off.
