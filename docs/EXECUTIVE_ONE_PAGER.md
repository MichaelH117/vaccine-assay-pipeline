# Vaccine assay pipeline: executive one-pager

**Synthetic data. A demonstration, not a deployed or validated system.** 2026-10-30.

**The problem.** Before a vaccine trial can say "the vaccine group made more antibody than placebo", an assay lab
has to run thousands of serum samples on 96-well plates, fit a standard curve to each plate, throw out the plates
that fail, re-run the samples that need it, and prove that no record was changed without a trace. Done by hand, each
of those steps is a place where a bad plate or a quietly edited record can reach the trial's statistics.

**What was built.** One command takes raw plate-reader files and lab records through a mini-LIMS with an
append-only audit trail, 4PL curve fits, QC rules, reportable-result selection and dbt marts, and produces plate
decisions, a re-assay list, immunogenicity tables and a detection scorecard. Thirteen problems are planted on
purpose (a mis-pipetted plate, swapped samples, a missing custody step, a late entry, a tampered audit row, a
record edited by direct SQL and more), and the pipeline reports how many it caught.

**Results (latest recorded run, seed 42).**
| | |
|---|---|
| Planted problems caught | **13 of 13** (14 of 14 affected records) |
| Samples flagged with no planted cause | **1 of 360** (0.277%), traced to a second catch of a planted tamper |
| Plates rejected with no planted cause | **0 of 13** |
| Automated checks | **pytest 245 passed, 0 failed; dbt 145 of 145 passed** |
| Same seed, run twice | **58 of 60 output files byte-identical**; the 2 others differ only in run-time clock columns |
| Synthetic trial readout, Day 29 | Vaccine GMT 4,332 AU/mL (95% CI 3,077-6,100), seroresponse 56 of 58; Placebo GMT 219, 0 of 60 |

**What it cost to get right.** Code review raised 12 findings; QA and the flaw hunt logged 12 bugs (8 fixed, 4
open with owners). The most important: tamper
detection originally watched the audit log but not the records themselves, so a direct edit of a record went unseen.
That was reversed in [ADR 007](team/adr/007-detect-record-edits-reconciliation-and-anchor.md) and is now a
planted, scored check.

**What is still open.** A re-run deletes the previous audit trail; detection is not prevention; there is no real
authentication; QC thresholds are demo defaults ([KNOWN_ISSUES.md](KNOWN_ISSUES.md)). A 10x study builds in 50.9 s
on a laptop and a 100x study (36,000 samples) in 528.2 s; one quadratic step takes 221.1 s of that and has a
known fix ([SCALE_AND_COST.md](SCALE_AND_COST.md)).

**Decision asked of a reader.** None: this is a demonstration of practice. The full story is in
[CASE_STUDY.md](CASE_STUDY.md).
