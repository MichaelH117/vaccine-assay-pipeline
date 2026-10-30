# Brief: vaccine-assay-pipeline

One page. Owner: Principal Engineer seat, 2026-10-30. Full product spec: [team/SPEC.md](team/SPEC.md).
**All data is synthetic.** This is a demonstration. It is not a validated system and has no real users.

## Who the user is
- **Primary: the assay lab's data reviewer** in a vaccine-trial clinical immunology lab (GCLP). Every day this person
  decides which 96-well plates pass QC, which samples must be re-run, and whether the record trail would survive an
  audit.
- **Secondary: the study statistician**, who needs GMT, GMFR and seroresponse by group and visit from results they
  can trust, and **QA / data integrity**, who must show who changed what, when and why.

## The decision it supports
"Can these plate results be released to the trial's statisticians, and if not, exactly which plates and samples go
back to the bench, and why?" Today (in the scenario) that answer comes from analysts reading plate-reader exports and
LIMS screens by hand.

## Goals
1. One command turns raw plate-reader CSVs and LIMS records into accepted/rejected plates, reportable results,
   immunogenicity tables and a re-assay list, each with a reason code.
2. Every LIMS and result record is written through an append-only, audited path; edits outside it are detected.
3. The pipeline proves its own checks work: it plants known problems and reports how many it caught, next to its
   false-positive rate.

## Non-goals
- Not a validated GxP system, not Part 11 compliant, no e-signatures or real authentication (SPEC section 6).
- No real assay, trial or patient data, and no claim about which LIMS or assays a real lab uses.
- No statistical analysis plan: GMT, GMFR and seroresponse follow common published definitions, not a protocol.
- No LLM. Not a dashboard product: a dashboard spec and PNG charts only.

## Success metric, baseline and guardrails
| | Definition | Target | Latest run (seed 42) |
|---|---|---|---|
| **Primary: required recall** | planted problems caught / planted, problem = one injected issue (INJ-2's swap = 1 problem, 2 records) | 100% | **13 of 13** (14 of 14 records) |
| Guardrail: sample false-positive rate | samples with a blocking flag that no planted problem explains / all samples | ≤ 5% (config `max_unexplained_flag_pct`) | **1 of 360 (0.277%)**, explained in FLAW_HUNT FH-05 |
| Guardrail: plate false-reject rate | rejected plates with no planted cause / all plates | 0 | **0 of 13** |
| Guardrail: build health | dbt nodes passed; pytest | all pass | **dbt 145 of 145; pytest 245 passed, 0 failed** |
| Guardrail: reproducibility | same seed, same outputs | identical | **58 of 60 output files byte-identical**; the other 2 differ only in run-clock columns (FLAW_HUNT FH-01) |

**Baseline.** The scenario's baseline is manual review, and it was not measured: there is no real lab here, and we do
not invent a "hours saved" number. The measurable baseline inside the project is the pipeline before the fix round:
a direct SQL edit of a record went undetected (REVIEW F1), so INJ-11 would have scored 0 of 1, and one `inf` cell
aborted the whole run (BUG-001).
