# Postmortem: the QA test harness stopped planting INJ-11 after the pipeline changed

Blameless format (Google SRE style). Date of incident: 2026-10-30. Author: Principal Engineer seat, from the
HANDOFF.md entries of the GxP, Data Engineer and QA seats and the code as it stands. Synthetic data only. No real
lab, trial or person was affected; the "impact" is to this project's own evidence.

## Summary
A new planted problem, INJ-11 (a base-table row edited by direct SQL), was added to the pipeline's step 7. One test
helper, `tests/qa/qa_helpers.py::staged_build`, ran its own hand-copied version of step 7 and never got the change.
In every QA build that used the helper, INJ-11 was in the answer key but was never planted, so the scorecard reported
it as missed. Eight tests failed. Nothing wrong reached a reported result, because the tests went red, and the fix was
to stop keeping two copies of step 7.

## Impact
- 8 failing tests after the INJ-11 wiring landed (HANDOFF, DE follow-up entry). The suite could not be called green.
- Risk avoided: if the helper had been "fixed" by changing the expectation instead of the build, the QA edge tests
  would have kept running on a pipeline that is not the one that ships. Every QA result would then have described
  the wrong system.
- No result in `docs/results.json` was wrong. The real `pipeline.run.build()` planted and caught INJ-11 from the
  start (scratch build: dbt 137 of 137, "13 of 13 required planted problems caught").

## Timeline (2026-10-30, all seats)
1. GxP seat fixes BUG-005: adds record reconciliation and `generator/tamper.py::tamper_base_row`, and asks DE to wire
   INJ-11 into `run.py` step 7 in a stated order.
2. DE wires it: INJ-11 goes into the manifest and the required set, and step 7 inside `build()` now calls `tamper_base_row`.
3. A full run is started but killed by the operating system for low memory. The "after wiring" suite result is missing.
4. The next full run: **8 failures.**
5. DE triages and finds three separate causes:
   - `test_seed_sweep_recall_and_fp`: QA's test had `n_types == 8` hard-coded, and there are now 9 types. A stale
     expectation.
   - `test_summary_counts_problems_not_keys`: LIA's test used the hard-coded `REQUIRED` list (INJ-1..8). Another stale
     expectation.
   - `test_planted_problems_still_100pct_recall`: **the real one.** `staged_build` copied `build()` step 7 by hand, so
     it never called `tamper_base_row`.
6. Fix: step 7 becomes one function, `pipeline.run.integrity_step()`, called by both `build()` and `staged_build`.
   Both stale tests now read the required set from `config/qc_rules.yaml`.
7. Final `python -m pipeline.run --test`: **pytest 238 passed, 0 failed; dbt 137 of 137.**

## Root cause
Duplicated orchestration. QA needed to modify landing files between steps (truncate a plate, drop a custody row), so
`staged_build` re-implemented `build()`'s steps instead of calling them. That was reasonable when step 7 was "verify
the chain". Once step 7 gained an ordered sequence of six calls owned by another seat, the copy was a second source of
truth with no link to the first. Nothing failed at the moment of the copy; it failed the first time the original
changed.

Contributing factors:
- Three seats changed three files for one feature (GxP: tamper, DE: run.py, QA: helper) with no single owner of
  "step 7".
- The memory-killed run hid the failure for one round.
- Two tests hard-coded the list of required types instead of reading the config that defines it.

## What went well
- The scorecard compares what was planted with what was caught, so a missing plant shows up as a miss, not as silence.
- The failure surfaced in tests, before any results were published.
- Triage separated the one real defect from the two stale expectations, instead of updating all three asserts to pass.

## Fix and regression guard
- **Fix:** `pipeline/run.py::integrity_step` is the only step 7. Its docstring says it is shared with
  `staged_build` "so the two cannot drift apart"; `tests/qa/qa_helpers.py` line 45 calls it.
- **Regression test:** `tests/qa/test_qa_pipeline_edges.py::test_planted_problems_still_100pct_recall` fails if any
  planted problem in a staged build is not detected. `tests/qa/test_qa_run_edges.py::test_seed_sweep_recall_and_fp`
  fails if the number of required types planted differs from the config.
- **Proved it can fail:** removing INJ-11 from the generator makes the seed sweep fail (6 failed, 1 passed), as shown
  in [FLAW_HUNT.md](FLAW_HUNT.md) FH-04, row c2.

## Follow-ups
| Action | Owner | Status |
|---|---|---|
| Make `integrity_step` the single step 7 | data-engineer | Done 2026-10-30 |
| Read required INJ types from config in the seed sweep and the summary test | data-engineer | Done 2026-10-30 |
| Give INJ-11 its own fast recall test and answer-key entry; the same mutation passes all 69 tests in the seat files today | analytics-engineer | Open: BUGS.md BUG-010 |
| Build into a temp folder and swap it in, so a killed run cannot leave a half-built `data/` | data-engineer | Open: KNOWN_ISSUES KI-02 |
| Rule for the team: a test helper may wrap pipeline steps but must not re-implement them | tech-lead | Proposed (OPERATING_MODEL.md change control) |

## Second incident, short form: BUG-007, a bad `--seed` deleted the previous run
QA ran `python -m pipeline.run --seed -1` while probing. `build()` called `_clean()` first and deleted
`data/landing`, `data/raw` and the DuckDB file, and only then did numpy reject the seed. Restored by a seed-42 rebuild;
`docs/results.json` was unchanged apart from the test counts. Root cause: validation ran after a destructive step.
Fix: `check_seed()` runs in `main()` and `build()` before `_clean()`. Regression tests:
`tests/test_outputs.py::test_negative_seed_rejected_before_cleanup` and
`tests/qa/test_qa_run_edges.py::test_invalid_seed_leaves_previous_data_alone`. The same lesson (do nothing destructive
before the run is known to be able to finish) is behind KI-02.
