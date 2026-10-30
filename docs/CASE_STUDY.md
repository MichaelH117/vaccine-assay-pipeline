# Case study: a vaccine-trial assay pipeline that proves its own checks

**Synthetic data throughout.** A portfolio project, built by Michael Hanson with a team of AI agent seats (product,
tech lead, data, lab informatics, QA, GxP validation, DevOps, principal engineer). It is not deployed, has no users
and is not a validated system. Short version: [EXECUTIVE_ONE_PAGER.md](EXECUTIVE_ONE_PAGER.md).

## 1. The problem
A vaccine trial's key lab number is antibody level by group and visit: geometric mean titer/concentration (GMT/GMC),
fold rise (GMFR) and the share of subjects who respond. Upstream of that number, a clinical immunology lab working
under GCLP has to:
- keep an unbroken chain of custody for every serum tube (collected, received, aliquoted, assayed, stored);
- fit a 4-parameter logistic standard curve per 96-well plate and read samples off it, never extrapolating;
- reject plates whose curve, standards, controls or blanks fail, and re-run their samples;
- pick one reportable result per sample when it was run more than once;
- prove, ALCOA+ style, who recorded what, when and why, and that nothing changed silently.

Each step is a chance for a bad plate or an edited record to reach the statistics. The brief
([BRIEF.md](BRIEF.md)) names the decision the project supports: *can these results be released, and if not, which
plates and samples go back to the bench and why?*

## 2. What was built
```
plate-reader CSVs + LIMS records (synthetic, seeded, 13 planted problems)
  -> mini-LIMS: audited inserts only, hash-chained audit log, checkpoints, reconciliation, external anchor
  -> ingest: read-only raw copies + SHA-256, plate map, ID check
  -> 4PL fit per plate -> QC rules -> accept/reject plate -> reportable result per sample
  -> dbt: staging, integrity (custody, ALCOA+), core, marts (immunogenicity, lab KPIs, scorecard) + 103 dbt tests
  -> CSV/Parquet exports, PNG charts, docs/results.json
```
Seven ADRs record the choices ([team/adr/](team/adr/)), one of which reverses part of an earlier one.

## 3. Results (seed 42, from [results.json](results.json))
- **Detection:** 13 of 13 required planted problems caught (14 of 14 affected records), across 9 problem types.
- **Guardrails:** 1 of 360 samples with an unexplained flag (0.277%); 0 of 13 plates rejected without a planted cause.
- **Build:** dbt 145 of 145 nodes passed (34 models, 111 tests); pytest 245 passed, 0 failed (356.12 s).
- **Lab outcome:** 13 plates (10 first runs, 3 repeats), 2 rejected (PLATE-003 control out of range; PLATE-007
  failed fit and standard recovery); 358 reportable results; 2 missing (the swapped pair, by design); 80 rows on the
  re-assay list (22.2% of samples).
- **Synthetic readout, Day 29:** Vaccine GMT 4,332 AU/mL (95% CI 3,077-6,100, n = 58), GMFR 16.6, seroresponse
  56 of 58 (96.5%); Placebo GMT 219 (n = 60), seroresponse 0 of 60.
- **Reproducibility (re-verified 2026-10-30):** 58 of 60 output files byte-identical across two runs; the DuckDB file
  and anchor differ only in run-clock columns (30 of 37 tables identical, 7 clock-only, 0 other differences).

## 4. How it was, and how we fixed it
| What we found | How | Fix | Guard |
|---|---|---|---|
| Tamper detection covered the audit log, not the records: a direct `UPDATE` of a custody row went unseen | Tech Lead code review (F1), QA (BUG-005) | Reconciliation of every base row against its audit payload; ALCOA-O2 RECORD_MISMATCH; new planted problem INJ-11; ADR 007 supersedes ADR 001's detective control | `test_base_row_edit_is_found_with_field_diff`; fails when the check is removed (FLAW_HUNT FH-04b) |
| Deleting the newest audit rows left a valid, shorter chain | QA (BUG-004), review (F5) | Checkpoints per write plus a read-only anchor file | `test_tail_truncation_caught_by_checkpoint`, `test_forger_who_rewrites_checkpoints_is_caught_only_by_external_anchor` |
| One `inf` in an OD cell aborted the whole run | QA (BUG-001, High) | Non-finite and out-of-range ODs reject the plate, run continues | `test_infinite_od_does_not_abort_run` |
| INJ-5 could score as "caught" because a broken curve also failed the controls | Review (F3) | Masking rule; sandbox tests remove the flag and expect a miss | `test_inj5_not_detected_without_ctrl_oor` |
| A scorecard test could never fail | Review (F6) | Hand-written answer key | `test_caught_by_matches_hand_written_answer_key` |
| A bad `--seed` deleted the previous run's data | QA hit it for real (BUG-007) | Validate before cleaning | `test_invalid_seed_leaves_previous_data_alone` |
| The QA harness had a hand copy of step 7 and stopped planting INJ-11 | 8 failing tests | One shared `integrity_step` | [Postmortem](POSTMORTEM_2026-10-30_INJ11_harness_drift.md) |
| Fast recall tests skip INJ-11; a dropped landing column loads as NULLs | This flaw hunt | Logged BUG-010, BUG-011 | [FLAW_HUNT.md](FLAW_HUNT.md) |

## 5. Decisions and trade-offs
- **DuckDB, not PostgreSQL** ([ADR 001](team/adr/001-duckdb-append-only-by-api.md)): a laptop run with no server,
  paid for with detection instead of prevention. The cost is written down (KI-03), and the Postgres path is on the roadmap.
- **Detect record edits by reconciliation** ([ADR 007](team/adr/007-detect-record-edits-reconciliation-and-anchor.md)):
  reverses the hash-chain-only claim after review showed it watched the wrong object.
- **Fixed assay-level LLOQ for statistics** ([ADR 003](team/adr/003-seroresponse-and-lloq.md)), so a subject's
  baseline and Day 29 values use the same cut-off.
- **Python for audited writes and curve fits, dbt for everything derived** ([ADR 005](team/adr/005-python-vs-dbt-split.md)).
- **Pre-simulated repeat plates** ([ADR 006](team/adr/006-repeat-runs-and-reportable-selection.md)): one-pass run,
  at the cost of realism in scheduling.
- **Left the one false positive visible** instead of widening the answer key (FLAW_HUNT FH-05).

## 6. How it would run at a real lab
Roles, service levels, runbook and change control are in [OPERATING_MODEL.md](OPERATING_MODEL.md). Scale and cloud
cost estimates are in [SCALE_AND_COST.md](SCALE_AND_COST.md). Risks with owners: [RISK_REGISTER.md](RISK_REGISTER.md).
What comes next: [ROADMAP.md](ROADMAP.md).

## 7. Practices shown (no titles claimed)
Wrote a PR/FAQ spec with acceptance criteria; 7 ADRs, one superseding another; a code review with 12 findings; a
test plan mapping every acceptance criterion; 12 logged bugs, each fixed one guarded by a test; a GAMP 5-style
validation pack (DRAFT); a risk register; a flaw hunt with three planted bugs; a blameless postmortem; scale
measurements at 1x, 10x and 100x.
