# HANDOFF log

## 2026-10-29: Product Owner
- **What I did:** Wrote SPEC.md. It covers:
  - the PR/FAQ
  - a terms table with source URLs (4PL, LLOQ/ULOQ, GMT, GMFR, seroresponse, GCLP, ALCOA+)
  - Pfizer Pearl River grounding
  - users and workflow
  - 12 user stories (US-1 to US-12) with testable acceptance criteria
  - 8 injected problems (INJ-1 to INJ-8)
  - out-of-scope list, job-posting map, and 5 open decisions (D1 to D5)
- **Files changed:** docs/team/SPEC.md (new), docs/team/HANDOFF.md (new).
- **Checks run:** Web searches only (6 queries). No code exists yet, so no tests.
- **Open issues:**
  - The 2 LinkedIn posting URLs come from TEAM.md and were not re-opened (they may be closed).
  - The FDA data-integrity Q&A link was not opened: UNVERIFIED.
  - The exact ICH M10 calibration thresholds were not read from the PDF: UNVERIFIED. All thresholds live in config.
  - Merck, Aquestive, and Veeva postings have no URLs: UNVERIFIED.
  - Decisions D1 to D5 need Michael. Defaults: DuckDB, ELISA IgG (GMT/GMC), 4-fold seroresponse, Power BI.
- **Next:** tech-lead (DESIGN.md, TASKS.md).

## 2026-10-29: Tech Lead
- **What I did:** Wrote the design from SPEC.md, using the EM's decisions (D1 DuckDB, D2 ELISA GMT/GMC, D3 default seroresponse, D4 Power BI, D5 stretch only). Mirrored the clinical-data-review layout: a `pipeline` package, `python -m pipeline.run [--test]`, a dbt project with copied schema macro, `tests/conftest.py` session build fixtures, a local `.venv`. Added only scipy and matplotlib (plus pyyaml, which dbt already brings).
  - DESIGN.md: architecture, folder layout with per-seat file ownership, all table/column contracts, Python function signatures, the full `config/qc_rules.yaml` key list, test strategy, 12 risks.
  - ADRs 001-006: DuckDB with append-only by API + hash chain; ELISA AU/mL labelled GMT/GMC; seroresponse with a fixed assay LLOQ; 4PL via curve_fit; Python vs dbt split with one config passed as dbt vars; repeat runs pre-simulated by the generator.
  - TASKS.md: 10 DE, 8 GXP, 7 LIA, plus TL/QA/OPS tasks. Every US-1..US-12 and INJ-1..INJ-8 maps to a task.
- **Files changed:** docs/team/DESIGN.md, docs/team/TASKS.md, docs/team/adr/001..006 (all new), docs/team/HANDOFF.md.
- **Checks run:** None (docs only, no code yet). I read clinical-data-review's run.py, conftest, dbt project, and pyproject to copy its conventions.
- **Open issues:**
  - DuckDB cannot block UPDATEs itself (no triggers). The hash chain only detects tampering (ADR 001, R1).
  - The dbt Python model importing `pipeline.stats` is the most fragile piece. A fallback is written down (R4).
  - All QC thresholds are still UNVERIFIED against ICH M10.
  - The SPEC says `python -m vap run`. The design uses `python -m pipeline.run` as the EM asked. The Product Owner should update the SPEC wording.
- **Next:** In parallel: data-engineer (DE-01, DE-02), gxp-validation-engineer (GXP-01 first, then GXP-02), Lab Informatics Analyst (LIA-01 to LIA-03).

## 2026-10-29: GxP Validation Engineer: hand-over point 2 (GXP-01 ready)
- `pipeline/audit.py` is in place with the DESIGN 4 signatures: `init_audit`, `insert_records`, `correct_record`, `update`/`delete` (always raise `AppendOnlyError`), `ChainResult`, `verify_chain`. `tests/test_audit.py`: 23 passed.
- Notes for DE-03: `table` is `"schema.table"` and must already exist (schema.py DDL); call `init_audit(con)` before the first insert. Key columns must be non-null and unique; re-inserting an existing key raises `AppendOnlyError` (no silent overwrite). `performed_by` and `reason` must be non-blank. Extra df columns not in the table raise `ValueError`. 20k rows insert in about 0.5 s.

## 2026-10-29: Data Engineer (hand-over point 1: DE-01 done)
- Skeleton is in: `pipeline/config.py` (`ROOT`, `CONFIG_PATH`, `Paths`, `default_paths`, `load_rules`, `dbt_vars`), `config/qc_rules.yaml` (every key in DESIGN section 5), dbt project `vaccine_assay_pipeline` (profile env var `VAP_DB_PATH`, schema macro), `pyproject.toml`, `requirements.txt` (unpinned; OPS pins).
- **dbt var names** (flat, read with `var('<name>')`; no defaults in dbt_project.yml, `run.py` passes them):
  `rule_version`, `assay_lloq_au_ml`, `lloq_impute_factor`, `default_dilution`, `reassay_dilution_factor`, `custody_steps` (list),
  `max_freeze_thaw`, `late_entry_hours`, `seroresponse_fold`, `ci_level`, `baseline_visit`, `max_unexplained_flag_pct`, `expected_flags` (dict INJ-n -> list).
- **Staging models (coming in DE-08)**, one view per source table, same columns: `stg_users`, `stg_subjects`, `stg_samples`, `stg_aliquots`,
  `stg_custody_events`, `stg_plate_runs`, `stg_raw_files`, `stg_plate_map`, `stg_well_reads`, `stg_ingest_errors`, `stg_curve_fits`,
  `stg_std_recovery`, `stg_control_results`, `stg_sample_results`, `stg_qc_flags`, `stg_plate_status`, `stg_reportable_selection`,
  `stg_audit_log`, `stg_chain_verify`, `stg_file_integrity`, `stg_injected_problems`.

## 2026-10-29: GxP Validation Engineer (GXP-01 to GXP-05, Phase 0/1)
- **What I did:**
  - GXP-01 `pipeline/audit.py`: append-only write API per DESIGN 4 (batch insert + audit rows in one transaction, duplicate-key refusal, required who/why, `correct_record` appends CORRECTION rows with `supersedes_seq`, `update`/`delete` raise, SHA-256 hash chain, `verify_chain`).
  - GXP-03 `generator/tamper.py` (INJ-7: back-dates `performed_at` in one custody event's audit row by direct SQL) and `pipeline/integrity.py` (`write_chain_verify`, `rehash_raw_files`, `sha256_file`).
  - GXP-04/05 dbt `integrity/` models: `v_custody_status`, `custody_flags` (GAP / ORDER on first occurrence / FREEZE_THAW), `alcoa_findings` (A1 NO_PERFORMER, A2 UNKNOWN_USER, C1 LATE_ENTRY, O1 HASH_MISMATCH, CM1 CUSTODY_GAP), `_integrity.yml` dbt tests.
  - GXP-02 `docs/validation/`: VALIDATION_PLAN, URS (URS-01..28 traced to ACs), RISK_ASSESSMENT (F1..F15 H/M/L + residual risks), ALCOA_CHECKLIST (all 9 attributes with evidence); TRACEABILITY and VALIDATION_SUMMARY marked DRAFT (final at GXP-07). All say "demo, not a validated system".
  - GXP-06 test written early (skips until `built` exists).
- **Files changed:** pipeline/audit.py, pipeline/integrity.py, generator/tamper.py, dbt/models/integrity/{v_custody_status,custody_flags,alcoa_findings}.sql, dbt/models/integrity/_integrity.yml, tests/test_audit.py, tests/test_custody.py, tests/test_alcoa.py, tests/integrity_sql.py (new GXP test helper: renders the integrity SQL with the real `dbt_vars` and runs it on fixture staging tables), docs/validation/*.md (6 files).
- **Checks run:** `.venv\Scripts\python -m pytest tests/test_audit.py tests/test_custody.py tests/test_alcoa.py -q -p no:cacheprovider` -> **37 passed, 8 skipped** (the 8 are full-build tests waiting for the `built`/`clean_built` fixtures). `ruff check` on my files: all checks passed. Perf: 20k-row insert 0.48 s, verify 0.26 s.
- **Not run:** `dbt build` on the integrity models (no staging models yet). SQL logic is tested via the shim only (deviation DV-01).
- **Requests to other seats:**
  - **DE (run.py / DE-08):** integrity models `ref()` these staging names with DESIGN 3 column names: `stg_samples`, `stg_aliquots`, `stg_custody_events`, `stg_users`, `stg_file_integrity` (from `audit.file_integrity`). Please also stage `audit.chain_verify` for the scorecard. Vars used: `custody_steps`, `max_freeze_thaw`, `late_entry_hours` (already in your `DBT_VARS`, thanks).
  - **DE (run.py order):** `init_audit(con)` before the first insert; `tamper_audit_row(con, event_id)` after all audited writes; then `write_chain_verify(con, verify_chain(con))` and `rehash_raw_files(con, paths.raw)` before `dbt build`. `rehash_raw_files` looks files up as `raw_dir / lims.raw_files.file_name`.
  - **DE (ingest):** please make the raw copies read-only (`os.chmod(p, stat.S_IREAD)`); on Windows a read-only file cannot be deleted either, so `run.py` cleanup must chmod first (R6).
  - **TL:** I added column `checked_at` to `audit.file_integrity` (additive, DV-02). Please confirm.
- **Open issues:** API-only append-only (ADR 001) is listed as a known limitation and residual risk; a full-chain re-hash by someone with DB access is not detectable without an external anchor (documented).
- **Next:** DE (DE-03 can use `insert_records` now; DE-08/09 wiring), then GXP-06/07 in Phase 2 after QA-02.

## 2026-10-29: Lab Informatics Analyst (analytics-engineer seat), Phase 0 + 1 (LIA-01 to LIA-06)
- **What I did:**
  - LIA-01 `pipeline/stats.py`: `gmt_ci`, `gmfr_ci` (t-based on log10), `clopper_pearson`, `is_seroresponder` (ADR 003, baseline exactly at LLOQ uses the fold rule, exact 4x counts). `tests/test_stats.py`: hand-worked 5-subject GMT (100, CI 13.2-755) and GMFR (6.96, CI 3.39-14.3), seroresponse boundaries, Clopper-Pearson 0/n, n/n, 5/10.
  - LIA-02 `docs/METRICS.md`; LIA-03 `docs/DASHBOARD_SPEC.md` (Power BI, 3 pages, DAX per visual).
  - LIA-04/05 marts: `mart_immunogenicity.py`, `mart_lab_kpis.sql`, `mart_plate_qc.sql`, `detection_scorecard.sql`, `scorecard_false_positives.sql`, `_marts.yml`; `tests/test_scorecard.py`.
  - LIA-06 `pipeline/export.py` (`export_marts`, 9 tables, CSV + Parquet) and `pipeline/charts.py` (`render_charts`, 3 PNGs).
- **Files changed:** the files above (all new). Nothing outside my DESIGN section 2 ownership.
- **Checks run (real results):**
  - `pytest tests/test_stats.py`: **18 passed**. `ruff check` on my files: all passed.
  - Fixture dbt build (scratch project outside the repo: my marts + stub models over contract-shaped fixture tables, vars from `dbt_vars(load_rules())`): **PASS=45 WARN=0 ERROR=0** (5 mart models, 21 tests, 19 stub views). Mart values matched the hand calculations. `export_marts` wrote 18 files; `render_charts` wrote 3 PNGs, which I viewed.
  - **NOT run:** a dbt build on real upstream models (staging and core folders are still empty) and `tests/test_scorecard.py` (no `tests/conftest.py` / `built` fixture yet). No `docs/img/*.png` or `data/marts/` output exists in the repo yet.
- **Requests:**
  - **DE (staging/core):** my marts `ref()` these names: `stg_std_recovery, stg_control_results, stg_well_reads, stg_plate_map, stg_plate_status, stg_plate_runs, stg_curve_fits, stg_sample_results, stg_qc_flags, stg_custody_events, stg_samples, stg_aliquots, stg_chain_verify` (audit.chain_verify), `stg_injected_problems` (truth), plus `fct_reportable_result` (needs `visit_day` and `run_at`) and `reassay_list`. GXP's integrity models use the same `stg_<table>` convention.
  - **DE (run.py, DE-09):** after dbt, call `export_marts(con, paths.marts)` then `render_charts(con, paths.img)`. `run_dbt` must set `PYTHONPATH=ROOT` (the model also falls back to cwd and its parent).
  - **TL (contract):** DESIGN 3.3 `sero_N` collides with `sero_n` (DuckDB names are case-insensitive), so it is `sero_total`. Added columns: `visit_day`, `group_visit_key` (immunogenicity); `run_at, repeat_of_plate_id, converged, lloq_conc, uloq_conc, fit_a..fit_d` (plate QC); `scorecard_key, description, problem_detected` (scorecard). Please approve in DESIGN.
  - **All seats:** `key` is a DuckDB keyword; alias it as `... as key` (a bare alias is a parse error).
- **Open issues:** LIA-07 (`tests/test_kpis.py`) is Phase 2 and not started. FP definition counts blocking SAMPLE flags plus custody/ALCOA flags linked to a sample; BELOW_LLOQ is excluded (METRICS.md section 4).
- **Next:** DE (staging, core, run.py), then I run the real dbt build, test_scorecard and LIA-07; then qa-engineer.

## 2026-10-29: Data Engineer, Phases 0-2 (DE-01 to DE-09, plus stretch DE-10)
- **What I did:**
  - DE-01 skeleton/config (see hand-over note above). DE-02 `generator/generate.py`: 120 subjects, 360 samples, 13 plates (10 first runs + 3 pre-simulated repeats, ADR 006), INJ-1..8 (+ INJ-9/10 behind `--optional-problems`). Plate layout documented in the module docstring. Curve/noise tuned so ~99% of clean plates keep all 8 standards.
  - DE-03 `pipeline/schema.py` (DDL + `write_table` -> GXP's real `audit.insert_records`; no stub was ever needed) and `lims_load.py`. DE-04 `ingest.py`, DE-05 `curve.py`, DE-06 `qc.py`, DE-07 `reportable.py`.
  - DE-08 dbt: `_sources.yml`, 21 `stg_*` views, `fct_reportable_result`, `missing_results`, `reassay_list`, `_core.yml`, singular test `dbt/tests/assert_reportable_and_missing_disjoint.sql`. Every model has a description.
  - DE-09 `pipeline/run.py` (wires GXP tamper/verify/rehash and LIA export/charts in DESIGN order; per-build dbt target/log dirs next to the DB; `PYTHONPATH=ROOT`), `tests/conftest.py` (`built`, `clean_built`), tests for generator/ingest/curve/qc/reportable/outputs.
- **Checks run (real):**
  - `.venv\Scripts\python -m pipeline.run --test`: **pytest 122 passed** (0 failed, 0 skipped; GXP's 8 full-build tests now run), **dbt build 131 of 131 passed** (32 models, 99 tests), 59.5 s.
  - Scorecard seed 42: 12 of 12 problems (13 keys) detected, FP 0.0%. Seeds 1/2/3: 13/13 keys, FP 0.0%, dbt 131/131. `--optional-problems`: INJ-9 and INJ-10 detected.
  - Re-run: all 56 output files (landing, raw, marts CSV/Parquet, 3 PNGs, results.json) byte-identical by SHA-256. `ruff check` on my files: clean.
- **Contract notes for TL (please approve in DESIGN):**
  - DB file is `data/warehouse/vaccine_assay.duckdb`, not `assay.duckdb`: DuckDB names the catalog after the file, which clashes with schema `assay` (Binder "Ambiguous reference").
  - `qc_flags.flag_id` = `RULE:PLATE:sample_id` (`-` for plate flags, control level for CTRL_OOR). BELOW_LLOQ/ABOVE_ULOQ are only raised on ACCEPTED plates (rejected-plate curves are untrusted; those samples are on the re-assay list anyway). `sample_results.range_flag` is null when a plate has no curve.
  - Pipeline writes are audited with `performed_by = SYS-PIPELINE` (not in `lims.users`; ALCOA checks only look at custody events, so no findings).
  - Added columns: `fct_reportable_result.dilution`, `missing_results.detail/n_runs`, `reassay_list.resolved`. `reportable_selection` has one row per LIMS sample.
- **Open issues:** `README.md` does not exist yet, so the results block is skipped (OPS). `requirements.txt` is unpinned (OPS-01). `marts.detection_scorecard` has no ORDER BY (fine for tests; exports were still identical).
- **Next:** analytics-engineer (LIA-07), gxp-validation-engineer (GXP-06), then qa-engineer.

## 2026-10-29: Lab Informatics Analyst, Phase 2 (real-data verification + LIA-07)
- **What I did:**
  - Ran `pipeline.run.build(seed=42, inject=True)` into a scratch folder (outside the repo). dbt `run_results.json`: **131 nodes, 0 failures** (99 tests pass, 32 models success); my 5 marts + 21 mart tests are all in it (26 nodes, all pass/success).
  - `tests/test_scorecard.py` on `built`: **5 passed**. Recall 13/13 injected keys (INJ-1 to INJ-8, 12 problems), FP 0/360 samples = 0.00% (target <= 5%).
  - LIA-07 `tests/test_kpis.py` (new, 9 tests): recomputes every KPI from `lims.*`/`assay.*` in pandas, recomputes GMT/CI, GMFR and seroresponse with scipy directly (not `pipeline.stats`), checks AC-8.2 pairing and AC-8.5. **9 passed.**
  - Charts checked on the real DB: fixed the plate grid (PLATE-007 had 3 reasons overflowing the tile; now one per line, and repeat plates show "repeat of PLATE-xxx") and GMT axis ticks (were 6x10^3 style; now plain numbers with only the 2x/5x minor ticks labelled). Curve chart was already fine (PLATE-001, R2 0.9998).
- **Real results (seed 42):** Vaccine D29 GMT 3,927 (CI 2,880-5,353), GMFR 15.2, seroresponse 58/60 = 96.7% (88.5-99.6); Placebo D29 0/59 = 0% (0-6.1). Plates 11 accepted / 2 rejected of 13. Re-assay 22.2% (80/360). Median TAT 54.6 days.
- **Files changed:** `pipeline/charts.py`, `tests/test_kpis.py` (new), `docs/team/HANDOFF.md`.
- **Checks run:** full `pytest`: **131 passed** in 48.9 s (122 + 9 new). `ruff check` on my files: clean.
- **Open issues:**
  - The ALCOA numerator in test_kpis is read from `integrity.alcoa_findings` (GXP's logic, tested in test_alcoa.py), not re-derived; the denominator is recomputed.
  - The sero_N -> sero_total contract change still needs TL sign-off.
  - Median TAT of ~55 days reflects the generator's batch run dates. That is not a pipeline bug, but the README should frame it.
- **Next:** qa-engineer (and TL review).

## 2026-10-30: Tech Lead (contract decisions + code review)
- **What I did:**
  - Approved all 7 requested contract changes: DB file `vaccine_assay.duckdb`, `sero_total`, `file_integrity.checked_at`, `flag_id` = `RULE:PLATE:KEY`, LLOQ/ULOQ flags only on ACCEPTED plates, `SYS-PIPELINE` audit actor, and the added columns. They are recorded in DESIGN.md (v1.1, new section 10) and as amendments to ADR 001, 003 and 006.
  - Code review written to docs/team/REVIEW.md: 12 findings (1 High, 4 Medium, 7 Low).
- **Files changed:** docs/team/DESIGN.md, docs/team/adr/001, 003, 006 (amendments), docs/team/REVIEW.md (new), docs/team/HANDOFF.md. No product code changed.
- **Checks run:**
  - Read-only queries on the seed-42 DB. Results: 13 fits; PLATE-007 c = 10000 (at the bound) with R2 0.910; flag counts; 358 REPORTABLE + 2 NO_VALID_RESULT; scorecard 13/13; FP 0%.
  - I did not re-run pytest. A later read attempt failed because the DB file had been removed, presumably by a rebuild.
- **Open issues (top):**
  - F1 (GXP): the hash chain does not detect a direct edit of a base-table row; only audit_log edits are caught.
  - F2 (LIA/QA): the FP metric ignores plates rejected by mistake.
  - F3 (LIA/DE): cascaded CTRL_OOR can satisfy INJ-5 for the wrong reason.
  - F4 (DE): a fit pinned at a parameter bound counts as converged.
  - F5 (GXP): tail truncation of the audit log is undetected.
- **Next:** DE, GXP and LIA fix F1-F5. Then qa-engineer, who should add the F2 and F3 assertions to the edge tests.

## 2026-10-30: QA / Test Engineer (qa-engineer seat), QA-01 + QA-02
- **What I did:** black-box edge testing. Wrote `docs/team/TEST_PLAN.md`, which maps every AC to a test: 46 MET or MET (manual), 3 PARTIAL (AC-3.3, 4.1, 6.2), 2 NOT MET (AC-12.1 not documented yet, AC-12.3 unpinned: both are OPS-01). Added 79 tests under `tests/qa/`. Every open bug has a `xfail(strict=True)` test, so a fix makes it XPASS, the suite goes red, and the fixer removes the mark. Logged 9 bugs in `docs/team/BUGS.md`.
- **Files changed (all new):** tests/qa/qa_helpers.py, tests/qa/test_qa_parser.py, test_qa_audit_chain.py, test_qa_pipeline_edges.py, test_qa_run_edges.py, test_qa_immunogenicity_edges.py, test_qa_deliverables.py; docs/team/TEST_PLAN.md; docs/team/BUGS.md. No product code touched.
- **Checks run (real):** `.venv\Scripts\python -m pytest -q -p no:cacheprovider` -> **196 passed, 14 xfailed, 0 failed in 181 s** (131 seat tests + 65 QA passes + 14 QA xfails). `ruff check tests/qa`: all passed. Seeds 0/1/2/3/2^32-1/10^12: 100% recall, FP 0.0%, dbt 131/131 each.
- **Incident:** while probing, I ran `python -m pipeline.run --seed -1` against the repo. It deleted `data/landing`, `data/raw` and the DB before failing (BUG-007). I restored them with `python -m pipeline.run` (seed 42). The summary in `docs/results.json` was identical apart from `tests`.
- **Bugs:** BUG-001 High (one `inf` OD aborts the run), BUG-003 Medium (an unparseable plate's samples never re-assayed), BUG-006 Medium (duplicate/unknown plate file silent), BUG-007 Medium (bad seed wipes data), BUG-002 and BUG-008 Low: all owned by data-engineer. BUG-004 Medium (audit tail truncation/re-hash undetected) and BUG-005 Medium (a base-table edit is undetected): gxp-validation-engineer. BUG-009 Medium (unpinned deps, no README): devops-engineer.
- **Note for OPS:** the suite now takes about 3 min. `pipeline.run --test` is about 3.2 min, still under the 5-min target.
- **Next:** data-engineer (BUG-001 first), and gxp-validation-engineer (BUG-004/005, or document both as limitations). Then devops-engineer (OPS-01, BUG-009). Re-run QA after the fixes.

## 2026-10-30: Lab Informatics Analyst, fix round (REVIEW F2, F3, F6, F7, F11 + count reconciliation)
- **What I did:**
  - **F3:** `detection_scorecard.sql` now requires the expected rule *and* no masking flag on the same key. INJ-5 counts only if its plate has CTRL_OOR and no FIT_FAIL/STD_RECOVERY. The new column `masked_by` shows when a key was refused for this reason. Masking lists come from dbt var `masking_flags`, with default `{INJ-5: [FIT_FAIL, STD_RECOVERY]}`.
  - **F2:** `scorecard_false_positives` adds `plates_total, plates_rejected, plates_rejected_unexplained, plate_fp_pct, unexplained_plate_ids`. New test: the REJECTED set in `built` equals exactly the INJ-1/INJ-5 plates (seed 42: 2 of 13, plate FP 0).
  - **F7:** a sample flag is explained only when its code is in `expected_flags` for an injected key linked to that sample. Cross-plate matches are accepted, and METRICS.md says so.
  - **F6:** I replaced the test that could never fail. The new test checks a hand-written `caught_by` per INJ type and confirms each flag in the raw flag tables. Three sandbox tests run the compiled scorecard SQL on a copy of the DB:
    - INJ-5 is detected when nothing is changed.
    - INJ-5 is not detected once CTRL_OOR is removed.
    - INJ-5 is not detected once a FIT_FAIL is added (the cascade case).
  - **F11:** I added a unit test of `mart_immunogenicity.build_rows`. It checks that only paired subjects are used, that D1 has nulls, that a subject with no D1 is excluded, and that an exactly-4x rise counts.
  - **Counts:** new one-row mart `scorecard_summary` (also exported). Shared list model: `scorecard_expected_flags`.
    - The unit is the **problem**. INJ-2 is one problem with 2 keys.
    - Seed 42 headline: "12 of 12 required planted problems caught (13 of 13 affected records); 0 of 0 optional".
    - With `--optional-problems`, the same headline ends "...; 2 of 2 optional" (INJ-9, INJ-10).
    - Required types = dbt var `required_inj_types` (default INJ-1..8). Any other type, including GXP's planned direct-edit injection, is counted as optional until it is added to that var. It also needs an `expected_flags` entry, or it shows as a miss.
- **Files changed:** `dbt/models/marts/{detection_scorecard,scorecard_false_positives}.sql`, new `scorecard_summary.sql`, new `scorecard_expected_flags.sql`, `_marts.yml`, `pipeline/export.py`, `tests/test_scorecard.py`, `tests/test_kpis.py`, `docs/METRICS.md`, `docs/DASHBOARD_SPEC.md`.
- **Checks run:**
  - `pytest tests/test_scorecard.py tests/test_kpis.py`: **20 passed**.
  - Full suite, first run (while other seats were mid-edit): 15 failed, 198 passed, 3 xfailed.
  - Full suite, second run: **237 passed, 1 failed**. The failure is `tests/qa/test_qa_run_edges.py::test_empty_plate_file_logged_and_run_continues` (`assert 13 == 12`), which tests DE's BUG-003 plate-count change. It is not in my files.
  - ruff on my files: clean.
- **Requests:**
  - **DE (run.py/README):** take the scorecard line from `marts.scorecard_summary.headline` (or `required_problems_detected` / `required_problems_planted` + `keys_*`), so README, results.json and the dashboard state one number. Optionally add `scorecard.required_inj_types` and `scorecard.masking_flags` to config and pass them through `dbt_vars()`; the marts already read those var names.
  - **DE:** `pipeline/qc.py:95` raises a SyntaxWarning (`'\.csv$'` needs a raw string).
  - **GXP:** for the new direct-edit injection, add its INJ id and flag code to `scorecard.expected_flags`. To make it count toward the required 100%, add it to `required_inj_types` as well.
- **Open:** if DE's BUG-003 fix adds an `INGEST_ERROR` reject reason, `mart_lab_kpis` has no `PLATE_REJECT_INGEST_ERROR` row yet. Such a plate already counts in `plates_rejected_unexplained` unless it is injected.
- **Next:** qa-engineer re-test; TL to close F2/F3/F6/F7/F11.

## 2026-10-30: GxP Validation Engineer (fix round: REVIEW F1/F5, BUG-004, BUG-005)
- **What I did:**
  - BUG-005 / F1: `audit.reconcile(con)` compares every live row of every audited table with its INSERT payload (RECORD_MODIFIED with a field diff, RECORD_DELETED, RECORD_UNAUDITED). `insert_records` now stores the row *as read back from the table* (so types match) and registers key columns in `audit.audited_tables`. `verify_chain` runs it as check `RECORD`. `integrity.reconcile_records(con)` writes `audit.record_reconciliation` (one `RUN` marker per run). `alcoa_findings` adds ALCOA-O2 `RECORD_MISMATCH` (source `gxp_audit.record_reconciliation`, new `dbt/models/integrity/_integrity_sources.yml`). Corrections never change base rows, so they are not mismatches.
  - BUG-004 / F5: every audited write appends to `audit.chain_checkpoint`; `verify_chain` checks them (`CHECKPOINT`). External write-once, read-only anchor: `integrity.write_chain_anchor(con, path)` + `verify_chain(con, anchor=path)` (`ANCHOR`). `ChainResult.check` and `audit.chain_verify.broken_check` say which check failed.
  - New planted problem INJ-11: `generator/tamper.py::tamper_base_row(con, event_id)` re-assigns `performed_by` of one custody event to another real user, directly in `lims.custody_events`, so only reconciliation can catch it.
  - Removed the 3 BUG-004/005 xfail marks in `tests/qa/test_qa_audit_chain.py`; BUGS.md marked FIXED. Validation docs bumped to v0.2: URS-29/30, RISK_ASSESSMENT F3/F3b + residual risks, ALCOA checklist, TRACEABILITY DRAFT, VALIDATION_SUMMARY DV-03..05.
- **Files changed:** pipeline/audit.py, pipeline/integrity.py, generator/tamper.py, dbt/models/integrity/alcoa_findings.sql, _integrity.yml, _integrity_sources.yml (new), tests/test_audit.py, tests/test_alcoa.py, tests/integrity_sql.py, tests/qa/test_qa_audit_chain.py (xfail marks only), docs/team/BUGS.md (status only), docs/validation/*.md.
- **Checks run:** full suite `.venv\Scripts\python -m pytest -q -p no:cacheprovider` -> **237 passed, 1 failed** (`test_qa_run_edges.py::test_empty_plate_file_logged_and_run_continues`, plate_status 12 vs 13: DE's BUG-003 work was landing during the run; a re-run of it alone plus all my files -> **71 passed**). My files + QA audit tests: 71 passed. ruff on my files: clean. The clean build's `chain_verify` is OK with reconciliation on, so there are no false RECORD issues on real data.
- **Requests (I did not edit these files):**
  - **DE, generator:** add an INJ-11 row to `injected_problems.csv` (key_type `event_id`, a custody event that is NOT already an INJ-3/4/7 key), on by default with `inject=True`.
  - **DE, run.py step 7, in this order:** `tamper_audit_row` (INJ-7) -> `tamper_base_row` (each INJ-11 event_id) -> `write_chain_verify(con, verify_chain(con))` -> `reconcile_records(con)` -> `rehash_raw_files(con, paths.raw)` -> after the dbt build (or at the end of step 7) `write_chain_anchor(con, paths.db.parent / "audit_anchor.json")`. Also, optionally, copy `head_seq`/`head_hash` into `docs/results.json` (REVIEW F5 suggestion) so the anchor lives outside `data/`. `_clean()` must chmod the anchor file before deleting it (read-only, R6).
  - **DE, config:** `scorecard.expected_flags` add `INJ-11: [RECORD_MISMATCH]`.
  - **LIA, scorecard:** nothing structural; `alcoa_findings` is already unioned. Please extend the recall test to INJ-11 once DE lands it.
  - **TL:** amend ADR 001 to say base rows are now reconciled and where the anchor lives; confirm DV-05 (audit payload = row as stored).
- **Open issues:** the anchor only protects the current run in the demo (the DB and `data/` are rebuilt each run); this is documented as a residual risk. The INJ-11 scorecard result is PENDING until DE/LIA wire it.
- **Next:** DE (INJ-11 + run.py wiring), LIA (recall test), then QA re-test and GXP-07.

## 2026-10-30: Data Engineer (fix round: BUG-001/002/003/006/007/008, REVIEW F3/F4/F8/F9/F12, INJ-11 + anchor wiring)
- **What I did:**
  - BUG-001/002/008 `parse_plate_csv`: rejects non-finite OD, OD outside new config keys `plate.min_raw_od` 0.0 / `plate.max_raw_od` 4.5 (demo defaults, **TL to confirm**), and gives separate shape / row-label / column-label messages.
  - BUG-006: a file whose name is not a planned plate in `lims.plate_runs` is still copied and hashed, but not parsed. It is logged in `assay.ingest_errors`, which names any file with the same SHA-256 as a duplicate upload.
  - BUG-003: the plate map of every planned plate is loaded. A planned plate with no usable reads gets a blocking `INGEST_ERROR` plate flag and status REJECTED. Its samples go on `reassay_list` and appear in `missing_results` as `PLATE_INGEST_ERROR`. `reportable.py` counts runs from the plate map.
  - BUG-007: `check_seed()` runs in `build()` and `main()` before `_clean()`.
  - F4: a fit that stops on a curve_fit bound is `converged=False` with the message "parameter at bound: ...". Its params and R2 are kept. PLATE-007 is now FIT_FAIL + STD_RECOVERY only.
  - F3 (qc side): no CTRL_OOR on a FIT_FAIL plate.
  - F8: a NaN mean OD gets no range label.
  - F9: a >ULOQ read on a rejected plate is suggested at dilution x10.
  - F12: `load_rules` checks that `assay_lloq_au_ml` = lowest standard x default dilution.
  - Not changed: F10 (DUP_CV near blank). There are no natural DUP_CV flags on seeds 42/1/2/3, and the behaviour is documented here for LIA's METRICS.md.
  - Turnaround: plates are now filled in order of receipt and run 7 days after the last sample on the plate is aliquoted. Receipt-to-assay is 6.6-16.2 days (TAT median 12.4 d, P90 16.0 d; it was about 55 d).
  - Wiring for GXP:
    - INJ-11 (`collected` event of a non-injected sample) is in the manifest and is required in `scorecard.required_inj_types`, with `expected_flags` `INJ-11: [RECORD_MISMATCH]`.
    - Step 7 order: tamper_audit_row, tamper_base_row, verify_chain, reconcile_records, rehash_raw_files, then `write_chain_anchor` to `data/warehouse/audit_anchor.json`. `_clean` chmods the anchor before deleting it.
    - The anchor head is NOT copied into results.json. The head hash covers real audit timestamps, so results.json would no longer be identical between runs.
  - Wiring for LIA:
    - `scorecard.required_inj_types` and `masking_flags` are in the config and passed through `dbt_vars()`.
    - results.json and the README block use `marts.scorecard_summary.headline`.
    - The SyntaxWarning in qc.py is fixed (raw string).
  - Tests: new unit tests for each fix. My xfail marks are removed in tests/qa. QA's `test_empty_plate_file_logged_and_run_continues` now expects 13 plate_status rows with REJECTED/INGEST_ERROR, because the old `== 12` assertion pinned BUG-003's behaviour. **QA please confirm.** BUGS.md: my 6 bugs are marked FIXED.
- **Checks run (real):**
  - Full pytest, before INJ-11/anchor wiring: **224 passed, 2 failed**. The failures were `test_alcoa_findings_on_fixture` (GXP mid-edit; passed on re-run) and the QA empty-plate test above (updated; passed on re-run: 8 passed).
  - Scratch build with all wiring (seed 42): **dbt 137 of 137 passed**. Headline "13 of 13 required planted problems caught (14 of 14 affected records); 0 of 0 optional". INJ-11 caught by RECORD_MISMATCH. Plates rejected: exactly PLATE-003 (CTRL_OOR) and PLATE-007 (FIT_FAIL, STD_RECOVERY). fp_pct 0.28. Anchor written.
  - ruff on my files: clean.
  - **NOT completed:** the final `pipeline.run --test` (full suite after the INJ-11 wiring) and the byte-identical re-run check. The system killed them for low memory, and the harness says not to restart them unasked. `data/` in the repo may be partial until the next run.
- **Open:** LIA: `mart_lab_kpis` has no `PLATE_REJECT_INGEST_ERROR` row; INJ-11 recall test pending. TL: confirm the raw OD range and the INGEST_ERROR rule code. OPS: README/Makefile/pins (BUG-009).
- **Next:** EM to re-run `.venv\Scripts\python -m pipeline.run --test` when memory allows, then LIA (INJ-11 test), QA re-test.

## 2026-10-30: Data Engineer (follow-up: 8 failures after INJ-11 wiring)
- **Root causes. None was a product bug; two stale expectations and one drifted test harness:**
  - `test_qa_run_edges.py::test_seed_sweep_recall_and_fp[*]` (QA's file): the test hard-coded `n_types == 8`, but INJ-11 makes 9. It now reads `len(scorecard.required_inj_types)` from the config. dbt itself passed on every seed.
  - `test_qa_pipeline_edges.py::test_planted_problems_still_100pct_recall`: QA's `tests/qa/qa_helpers.py::staged_build` copied `build()` step 7 by hand, so it never called `tamper_base_row`. INJ-11 was in the manifest but never planted. Fix: `pipeline.run.integrity_step()` is now the single step 7, called by both `build()` and `staged_build`, so the two cannot drift again (QA's file touched: helper import and one call).
  - `test_scorecard.py::test_summary_counts_problems_not_keys` (LIA's file): it used the hard-coded `REQUIRED` list (INJ-1..8). It now uses `scorecard.required_inj_types` from the config. The global `REQUIRED` and the hand-written answer key are unchanged; LIA still owns the INJ-11 recall test.
- **Checks run (one process at a time):** the 3 files: 38 passed. Final `.venv\Scripts\python -m pipeline.run --test`: **pytest 238 passed, 0 failed**; **dbt 137 of 137 passed** (34 models, 103 tests); headline "13 of 13 required planted problems caught (14 of 14 affected records)"; plate FP 0, sample fp_pct 0.28; 228.8 s.
- **Not re-run:** the byte-identical second-run check after this round (memory). The last confirmed identical run was before the fix round.

## 2026-10-30: Principal Engineer / Engineering Director (senior-scope pass + showcase README)
- **What I did:**
  - Wrote the senior-scope set in `docs/`: BRIEF, RISK_REGISTER (14 risks), KNOWN_ISSUES (15), FLAW_HUNT (10 failure modes, all with evidence, none "not checked"), POSTMORTEM_2026-10-30_INJ11_harness_drift (plus BUG-007 short form), SCALE_AND_COST, OPERATING_MODEL, ROADMAP, CASE_STUDY, EXECUTIVE_ONE_PAGER, and the showcase `README.md` (results table, Mermaid pipeline diagram, before/after table, links). Left a `## Quickstart` placeholder for devops-engineer.
  - ADR 007 (record reconciliation + anchor) now records the reversal; ADR 001 marked "partly superseded by ADR 007" (status line only).
  - 3 new infographics from recorded outputs (`tools/make_showcase_figures.py`): `docs/img/detection_scorecard.png`, `repeat_run_check.png`, `scale_profile.png`.
  - Evidence tools in `tools/`: `hash_outputs.sh`, `compare_duckdb_runs.py`, `schema_drift_probe.py`, `scale_probe.py`; raw evidence in `docs/evidence/`.
- **Checks run (real):**
  - **Repeat-run check (re-verified after the fix round):** two `python -m pipeline.run` runs (12.3 s, 10.6 s): 58 of 60 output files byte-identical, incl. all mart exports, 3 PNGs and `docs/results.json` (also identical to the pre-check copy). The DuckDB file and anchor differ; table-by-table: 37 tables, 30 identical, 7 differ only in run-clock columns, 0 other differences.
  - Planted bugs: DUP_CV threshold mutant -> 1 failed; reconciliation mutant -> 2 failed; INJ-11 removed from the generator -> **69 passed** in the seat files (gap, BUG-010), seed sweep 6 failed / 1 passed. All files restored and `cmp`-verified; the named tests pass again.
  - Schema drift probe: extra and renamed columns rejected; dropped column accepted silently (BUG-011).
  - Scale: clean 1x 14.9 s, 10x 50.9 s (3,600 samples, dbt 137/137). 100x 528.2 s (36,000 samples, 973 plates, 573,017 audit rows, dbt 137/137); reportable selection 221.1 s of it (quadratic `choose`).
  - I did not re-run the full pytest suite (no product code changed); README numbers are from `docs/results.json` (pytest 238 passed, 0 failed; dbt 137 of 137).
- **Bugs logged in BUGS.md:** BUG-010 (Low, LIA: fast recall test and answer key skip INJ-11 — the INJ-11 recall test is still missing), BUG-011 (Medium, DE: dropped landing column loads as NULL), BUG-012 (Low, LIA: no PLATE_REJECT_INGEST_ERROR KPI row; copied from HANDOFF open items).
- **Open / notes:** the auto results block written by `run.py::write_readme_results` prints `fp_pct` unformatted (`0.2777777777777778%`); a one-line format fix for DE. The single unexplained sample flag (SMP-00180, RECORD_MISMATCH from INJ-7) is intentionally left visible (FLAW_HUNT FH-05).
- **Files changed:** README.md (new); docs/{BRIEF,RISK_REGISTER,KNOWN_ISSUES,FLAW_HUNT,POSTMORTEM_2026-10-30_INJ11_harness_drift,SCALE_AND_COST,OPERATING_MODEL,ROADMAP,CASE_STUDY,EXECUTIVE_ONE_PAGER}.md (new); docs/team/adr/007-*.md (new); docs/team/adr/001 (status line); docs/team/BUGS.md (BUG-010..012); docs/img/{detection_scorecard,repeat_run_check,scale_profile}.png; docs/evidence/*; tools/*.
- **Next:** devops-engineer (pins, CI, .gitignore, Quickstart section; BUG-009). Then LIA (BUG-010, BUG-012), DE (BUG-011).

## 2026-10-30: Lab Informatics Analyst, BUG-010 and BUG-012
- **What I did:** BUG-010: `tests/test_scorecard.py` reads the required INJ types from config (now includes INJ-11), adds `INJ-11: RECORD_MISMATCH` to the answer key, and adds a fast INJ-11 detection test plus a guard that the answer key covers every required type. BUG-012: `PLATE_REJECT_INGEST_ERROR` KPI row (`mart_lab_kpis.sql`, METRICS.md), recomputed in `test_kpis.py`, plus a check that every reject reason has a KPI row. Both marked FIXED in BUGS.md.
- **Files changed:** `tests/test_scorecard.py`, `tests/test_kpis.py`, `dbt/models/marts/mart_lab_kpis.sql`, `docs/METRICS.md`, `docs/team/BUGS.md`, this file.
- **Checks run:** `pytest tests/test_scorecard.py tests/test_kpis.py`: **22 passed**. Proof on a scratch copy of the repo (generator in the real tree untouched): INJ-11 deleted gives **3 failed / 9 passed**; INJ-11 planted with its detector disabled gives **4 failed / 8 passed**. ruff clean. Per the EM, no full suite or pipeline run (RAM limit, DE running BUG-011).
- **Request (DE):** `tests/test_generator.py::test_every_required_inj_type_is_in_the_manifest` still hard-codes INJ-1..8. Read `scorecard.required_inj_types` instead.
- **Next:** EM final run, then qa-engineer.

## 2026-10-30: Data Engineer (Director flaw hunt: BUG-011 + reportable-selection performance)
- **BUG-011 FIXED:** `pipeline/lims_load.read_landing` takes `expected=` columns and raises `LandingSchemaError` (missing / unexpected columns). It is used for every lims.* CSV, `plate_map.csv` and `injected_problems.csv`. I also added 8 `not_null` dbt tests on staging contract columns. Tests: `test_ingest.py::test_missing_landing_column_fails_loudly` (subjects.site_id, custody_events.location, users.role) and `::test_missing_plate_map_column_fails_loudly`.
- **Performance:** `pipeline/reportable.py` is rewritten:
  - `load_runs()` joins one aggregated blocking-flag CTE instead of running a correlated subquery per row.
  - `choose()` sorts once, computes validity and reasons once, buckets the runs by sample in one pass, then walks the buckets. Previously it filtered the whole frame once per sample.
  - Equivalence test `test_reportable.py::test_grouped_selection_matches_old_scan_on_seed_42` keeps the old SQL and the old loop verbatim. On a seed-42 Python-only build it asserts identical runs frames, identical decisions, and identical stored `assay.reportable_selection`.
  - **Timing of `choose()` (old vs new, identical output):** 1x 0.49 s vs 0.004 s; 10x (4,400 runs) 9.06 s vs 0.013 s; 100x (44,000 runs) new 0.33 s. The old one was not run at 100x; the Director measured 221 s. These are synthetic replicas of the seed-42 runs, not a full 100x DB build.
- **For LIA:** `tests/test_generator.py` now reads the required and optional INJ lists from `config/qc_rules.yaml` (required = exactly the default manifest; every required type has `expected_flags`).
- **Checks (one process at a time, my files only):**
  - `tests/test_ingest.py` + reportable unit/equivalence tests: 23 passed.
  - `tests/test_generator.py` + reportable: 15 passed.
  - `dbt build --select staging` on a scratch seed-42 DB: PASS=67, ERROR=1. The error is the `fct_reportable_result` relationships test, which was pulled in by the selection and has no fct table in that Python-only DB, so it is not a real failure.
  - ruff clean.
  - **Not run:** the full pipeline (EM runs the final one).

## 2026-10-30: SRE / DevOps Engineer (OPS-01, BUG-009)
- **What I did:** pinned `requirements.txt` from `.venv` pip freeze (10 direct deps + dbt-adapters/dbt-common); wrote the README Quickstart (Windows + macOS/Linux, expected output); synced every count to `docs/results.json` (pytest 245 passed in 356.12 s; dbt 145 of 145, 34 models, 111 tests) in README, BRIEF, CASE_STUDY, EXECUTIVE_ONE_PAGER, FLAW_HUNT line 4 (postmortem and scale numbers left as historical, scale row annotated); `run.py` results block now prints `fp_pct` truncated to 3 dp (0.277%); `.github/workflows/ci.yml` (ruff + pytest, Python 3.13, ubuntu, no secrets/network/Ollama); `.gitignore` (venvs, data/, *.duckdb, dbt target/logs, caches, .env); `Makefile`; BUG-009 marked FIXED. `git init -b main`, one local commit, no remote.
- **Checks run (real):** ruff clean; ci.yml parses with PyYAML; schema drift probe re-run: 3 of 3 rejected. Fresh venv in scratchpad from the staged tree: `pip install -r requirements.txt` OK (256 s), imports OK, `python -m pipeline.run` exit 0 in 38 s (dbt 145/145, 13 of 13 caught), fast subset (curve, audit, stats, generator, qa_parser) 105 passed in 59 s. Temp venv deleted. Staged-file audit: 140 files, largest 156 KB PNG, no data/, *.duckdb, .env or secrets.
- **Not checked:** CI has never run on GitHub (not pushed); Linux run not executed locally (code review only: dbt path uses `os.name`, chmod read-only tests assume non-root, which holds on GitHub runners). Full pytest not re-run by me (EM's run: 245 passed).
- **Files changed:** requirements.txt, README.md, Makefile, .gitignore, .github/workflows/ci.yml, pipeline/run.py (one format line), docs/{BRIEF,CASE_STUDY,EXECUTIVE_ONE_PAGER,FLAW_HUNT}.md, docs/team/BUGS.md, this file.
- **Next:** product-owner, demo sign-off.

## 2026-10-30: Product Owner (demo sign-off, commit c3a93fd)
- **What I did:**
  - Checked all 51 SPEC acceptance criteria against the recorded outputs. I read only: results.json, data/marts CSVs, docs/img, evidence, TEST_PLAN, BUGS, validation, DASHBOARD_SPEC, requirements.txt and README.
  - Result: **49 MET, 2 PARTIAL (AC-9.2, AC-12.2), 0 NOT MET. Verdict: ACCEPTED for demo.**
  - Wrote 3 interview talking points.
  - Ran a README overclaim check.
- **Checks run:** none executed (no pipeline or pytest run, per the EM). The final-run line recorded in results.json is `"245 passed in 356.12s (0:05:56)"`, 0 failed / 0 skipped / 0 error; dbt nodes 145, passed 145, warn 0, failed 0. This was copied from results.json, not from a console.
- **Files changed:** docs/team/SIGNOFF.md (new), this file.
- **Open:**
  - EM: paste the raw pytest/dbt console tail here (AC-12.2).
  - QA: TEST_PLAN.md is stale (196 passed, dbt 131, old NOT MET/PARTIAL rows).
  - LIA: full METRICS.md vs SQL formula check (AC-9.2).
  - README: the clone URL implies a public repo; "CI runs on every push" but CI has never run; Quickstart says "about 5 minutes", but measured install plus tests is about 11 min.
  - PO: mark SPEC.md final, with INJ-11 required.
- **Next:** Michael, to approve the push after the README fixes.

## 2026-10-30, Engineering Manager: final run evidence (AC-12.2)
Command: `.venv\Scripts\python -m pipeline.run --test` (run alone, nothing else using the machine)
```
pytest: 245 passed in 356.12s (0:05:56)
dbt: {'nodes': 145, 'passed': 145, 'warn': 0, 'failed': 0, 'models': 34, 'tests': 111}; tests: 245 passed in 356.12s (0:05:56); done in 376.3 s
```
README fixes from SIGNOFF: install time now matches the measured 4.3 min, and CI is described as configured but not yet run. The git clone URL stays because it will resolve once Michael approves the push.
Still open: refresh TEST_PLAN.md counts (QA); hand-check the other 8 KPI formulas (AC-9.2).

## 2026-10-30, Design Lead: Quarto site (pharma theme), not committed
- **What I did:** Built a 6-page Quarto + Observable Plot static site in `site/` (renders to `site/_site`, GitHub Pages ready, not published): Overview (status badge, 5 KPI tiles with takeaway titles, "1 dot = 1 volunteer" unit chart with guess-then-reveal, visit/arm cross-filter), Follow one tube (play/pause stepper with stored vs recomputed SHA-256 per custody step; tamper switch shows the real `audit.chain_verify` / `record_reconciliation` output for INJ-7 and INJ-11, plus a labelled replay of the INJ-7 row before the edit), Lab QC (plate wall, rule slicer, 96-well map, 4PL curve with LLOQ–ULOQ band in plain words), Did we catch it? (13 one-line stories, false-alarm counts), Glossary (33 sourced terms; every acronym on every page auto-links with hover+focus tooltips), How it works (diagram, method, honesty notes). Calm clinical light theme with a selected dark mode; SYNTHETIC banner on every page.
- **Data:** `site/build_data.py` writes 7 JSON files (335 KB) from results.json, the marts and the read-only DuckDB. It reuses `is_seroresponder()` and `compute_row_hash()` and asserts (a) per-volunteer counts = `mart_immunogenicity` sero_n/sero_total for every group x visit and (b) the rebuilt pre-tamper INJ-7 row reproduces the stored hash. Both passed. No DuckDB-WASM.
- **Checks run (real):** `quarto render site` OK (6 of 6 pages, no warnings after all pages existed); headless Chrome DOM check found 0 OJS runtime errors on all 6 pages; page `scrollWidth` = 375 at a 375 px viewport on all 6 pages; WCAG contrast computed for every token pair (all text ≥ 4.5:1 after one fix); dataviz palette validator passed blue/orange in light and dark. Screenshots: `docs/img/site/*-{1440,375}.png` (12 files, 3.5 MB).
- **Files changed:** `site/` (new: _quarto.yml, 6 .qmd, theme*.scss, assets/site.css, assets/site.js, _banner.html, _status.qmd, build_data.py, data/*.json), `docs/img/site/` (new), `docs/team/DESIGN_REVIEW.md` (new), README.md (Interactive site section + screenshot table), .gitignore (`!site/data/`, ignore `site/_site/`, `site/.quarto/`), this file.
- **Open issues:** page titles are static text (true for seed 42); dot/well tooltips are mouse-only (table twins cover keyboard users); Observable Plot loads from the jsDelivr CDN; no real screen-reader test; 375 px screenshots come from an iframe harness in headless Chrome, not a phone.
- **Next:** principal-engineer (showcase README/case-study link check), then Michael to review and commit.

## 2026-10-30: Product Owner (SPEC v2, "real-industry" upgrade)
- **What I did:** Wrote `docs/team/SPEC_v2.md` from the vaccine R&D research file, SPEC v1, SIGNOFF and USER_TESTING. It has the question, 5 personas (U1-U5), an ontology/action table, PR/FAQ, 7 stories (US-13 to US-19, 50 ACs), new INJ-12..14 plus planted outcomes kept out of recall, four risks, cut line, out-of-scope list, job postings, and decisions D6-D10.
- **Stories:** US-13 vendor importers + detector (M), US-14 plate-map template + shifted-column check (S), US-15 20-serotype multiplex + bead-count QC (M), US-16 validation-style summary (S), US-17 NI / sensitivity / lot consistency (M), US-18 stage-gate + exec scorecard feed (S), US-19 regression + honesty (M).
- **Honesty:** no instrument-compatibility, validation or M10 claims (grep test AC-16.7); Prevnar 20 numbers labelled PUBLIC REFERENCE with the FDA memo URL; bead-count threshold marked UNVERIFIED demo default; IgG used where the real endpoint was OPA, stated in the FAQ.
- **Checks run:** none (document only). I did not reopen the job-posting URLs; they are marked as such.
- **Files changed:** docs/team/SPEC_v2.md (new), this file. Nothing under `site/` touched.
- **Open:** Michael decides D6-D10. Size is tight for 2 days; the cut order is in section 9.
- **Next:** tech-lead (DESIGN/TASKS for v2), after Michael's decisions.

## 2026-10-30 - ux-researcher (UX Researcher / Audience Lead)
- Did: aggregate audience research for 9 audiences (BLS CPS 2025 age/sex, NIDCD, NPWS, NCPA, Spencer Stuart, ESA/IGDA/GDC, DocSend, Ladders, Sapio, NN/g, Stanford), with design rules, rule-of-cool table, and synthetic persona inputs.
- Files: C:\Users\stimp\projects\dev-team\research\audience-data-2026-10-30.md (new). No product files changed.
- Checks: web sources fetched/searched; unsourced items marked UNVERIFIED.
- Open: device data, owner/F&I ages, game a11y guidelines not yet sourced.
- Next: design-lead (apply type/motion/color rules); ux-researcher to fold into PERSONAS.md.

## 2026-10-30, Design Lead: overview rebuilt as a "production story" + all 19 user-testing fixes, not committed
- **What I did:**
  - `index.qmd` is now a scroll story for a VP or board member. Above the fold: "On track", 56 of 58 vs 0 of 60,
    13 of 13 caught with 0 false plate rejections, "Tamper detected ✓" at row 2,130, each with a source link. Then
    6 chapters headed by their answers: where lab testing sits in a real program (Prevnar 20 FDA timeline, labelled
    public reference data), rising-antibody dots (pinned, 5 steps), a plate reader lit by real OD, 13 of 13 caught,
    a padlock chain that opens at row 2,130, and the decision being asked (status + confidence + caveat). It has a
    chapter rail, "Skip the story", count-ups, a Pause motion button and a still version under reduced motion.
  - The guess game was removed (Michael). The visit/group explorer moved to the new `results.qmd`.
  - All 19 USER_TESTING fixes are done (table in DESIGN_REVIEW.md), including the animation choreography.
  - `build_data.py` now also writes `site/_variables.yml` and asserts that the "On track" verdict holds.
- **For analytics-engineer (science wording; fixed on the site text only):**
  1. "stronger dilution" should read "higher dilution (for example 1 in 1,000)". Check the generator/scorecard
     descriptions and docs.
  2. INJ-6 is a duplicate %CV rule (CV > 20%), not "45% / disagreement". The real CVs are 50.5, 51.2 and 51.8%.
     Fix the INJ-6 wording wherever it appears outside the site (generator description, METRICS, docs).
- **Checks run (real):**
  - `build_data.py`: per-volunteer counts match the mart; pre-tamper seal reproduced; the 4 verdict asserts passed.
  - `quarto render site --output-dir _build`: 7 of 7 pages, no warnings, copied into `_site`. Plain
    `quarto render site` failed with os error 32 because the running server holds `_site` open. It worked once
    rendered elsewhere; the server is still up.
  - Headless Chrome, 42 runs (7 pages x 1440, 1280x720, 640, 375, forced-colors, reduced-motion): 0 OJS errors,
    0 overflow, 0 copy buttons, skip link on all, 0 SVG text under 14 px, 0 unnamed inputs, 0 uncaptioned tables.
- **Files changed:** site/index.qmd (rewritten), site/results.qmd (new), site/assets/story.js (new),
  site/assets/site.css, site/assets/site.js, site/_quarto.yml, site/_banner.html, site/_status.qmd,
  site/theme-light.scss, site/theme-dark.scss, site/qc.qmd, site/scorecard.qmd, site/tube.qmd, site/about.qmd,
  site/glossary.qmd, site/data/glossary.json, site/build_data.py, site/_variables.yml (generated),
  docs/img/site/*.png, README.md, docs/team/DESIGN_REVIEW.md, this file.
- **Open:**
  - No real screen-reader or phone test.
  - Takeaway titles were not restated by a reader.
  - Story order and palette are still Michael's call.
  - If you want `site/_variables.yml` to stay out of git, add it to .gitignore. It is regenerated by
    build_data.py, but the site needs it to render.
- **Next:** ux-researcher (re-run the panel and the 5-second test), then analytics-engineer for the 2 wording items.
