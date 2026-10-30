# TASKS: vaccine-assay-pipeline

Owner: Tech Lead seat. 2026-10-29. Read DESIGN.md (sections 2 to 5) and the ADRs first. Each task lists its stories,
the files it owns, and what it needs from others. File ownership follows DESIGN.md section 2. Do not edit files you
do not own.

Seats: DE = data-engineer, LIA = analytics-engineer (Lab Informatics Analyst), GXP = gxp-validation-engineer,
QA = qa-engineer, OPS = devops-engineer (light duty), TL = tech-lead. ml-engineer: no tasks (no LLM in v1).

## Build order

- **Phase 0 (start now, all three in parallel, no dependencies between them):** DE-01, DE-02 | GXP-01, GXP-02 | LIA-01, LIA-02, LIA-03
- **Phase 1 (parallel, against the table contracts):** DE-03 to DE-08 | GXP-03 to GXP-05 | LIA-04 to LIA-06
- **Phase 2 (integration):** DE-09 (wires everything into `run.py`), then LIA-07, GXP-06
- **Phase 3:** TL-01 review, then QA-01/02, GXP-07, OPS-01, product-owner demo sign-off
- **Stretch (D5, only if Phase 2 is done on day 1):** DE-10, GXP-08

Hand-over points (put a line in HANDOFF.md when each is done):
1. DE-01 done: the repo skeleton, `config/qc_rules.yaml`, and `pipeline/config.py` exist. Everyone can import them.
2. GXP-01 done: `pipeline/audit.py` has `insert_records`. DE-03 needs it. Until then DE may write through a
   local stub with the same signature, but must not commit the stub.
3. DE-08 done: a full DB with `lims.*`, `assay.*`, staging and core models. GXP and LIA switch from fixtures to real data.

---

## data-engineer (DE)

| ID | Task | Stories / ACs | Owns (files) | Needs |
|---|---|---|---|---|
| DE-01 | Repo skeleton copied from clinical-data-review: `.gitignore`, `pyproject.toml`, `requirements.txt` (that stack + scipy, matplotlib, pyyaml), `.venv`, `config/qc_rules.yaml` with **every** key in DESIGN section 5, `pipeline/__init__.py`, `pipeline/config.py` (`Paths`, `default_paths`, `load_rules`, `dbt_vars`), dbt project skeleton (`dbt_project.yml`, `profiles.yml` with `VAP_DB_PATH`, `macros/generate_schema_name.sql`). Test: `dbt_vars()` returns all (dbt) keys. | US-12 (AC-12.3), SPEC section 4 config | listed files | nothing |
| DE-02 | Generator: subjects, samples, aliquots, custody events (with plate_id and well on `assayed`), users, plate_runs, plate_map, raw plate CSVs, repeat plates (ADR 006), `injected_problems.csv` with INJ-1 to INJ-8. `inject=False` gives clean data. Tests: SHA-256 identical for the same seed; every INJ type present; clean Vaccine D29 GMT >= 4x baseline and Placebo GMFR in 0.8-1.25 (computed from the generator's true concentrations); synthetic ID patterns only. | US-1 (AC-1.1 to 1.5), INJ-1 to INJ-8 | `generator/__init__.py`, `generator/generate.py`, `tests/test_generator.py` | DE-01 |
| DE-03 | `pipeline/schema.py` (DDL for `lims.*`, `assay.*`) and `pipeline/lims_load.py`: landing CSVs into `lims.*` through `audit.insert_records`. | US-2 (AC-2.1), US-3 (AC-3.1) | `pipeline/schema.py`, `pipeline/lims_load.py` | GXP-01 |
| DE-04 | `pipeline/ingest.py`: copy plate CSVs to `data/raw/` and make them read-only, store SHA-256 in `lims.raw_files`, `parse_plate_csv` (wrong shape raises `PlateFormatError`, logged to `assay.ingest_errors`, run continues), plate-map join, blank correction, well-level ID_MISMATCH against custody `assayed` events. Tests: good file gives 96 rows; 7x12 and non-numeric files are rejected without crashing; INJ-2 gives exactly 2 ID_MISMATCH flags. | US-4 (AC-4.1 to 4.4), US-3 (AC-3.5) | `pipeline/ingest.py`, `tests/test_ingest.py` | DE-03 |
| DE-05 | `pipeline/curve.py`: `four_pl`, `inverse_four_pl`, `fit_plate` (ADR 004), `fit_all` writing `curve_fits`, `std_recovery`, `control_results`, `sample_results`. Tests: no-noise curve recovers c within 1%; inverse(four_pl(x)) == x; non-converging input gives `converged=False`, not an exception; out-of-range OD gives `<LLOQ`/`>ULOQ` with a null concentration; contiguous-range rule. | US-5 (AC-5.1 to 5.5) | `pipeline/curve.py`, `tests/test_curve.py` | DE-01 (pure functions); DE-04 for `fit_all` |
| DE-06 | `pipeline/qc.py`: FIT_FAIL, STD_RECOVERY, CTRL_OOR, BLANK_HIGH, DUP_CV, BELOW_LLOQ, ABOVE_ULOQ into `assay.qc_flags` (with rule_version, measured_value, threshold, blocking); `assay.plate_status`. Tests: one test per rule at the threshold boundary; INJ-1 and INJ-5 plates REJECTED; any plate flag means REJECTED. | US-6 (AC-6.1 to 6.5) | `pipeline/qc.py`, `tests/test_qc.py` | DE-05 |
| DE-07 | `pipeline/reportable.py`: latest valid run per sample, written through `insert_records` with a reason (ADR 006). | US-7 (AC-7.2) | `pipeline/reportable.py`, `tests/test_reportable.py` | DE-06, GXP-01 |
| DE-08 | dbt staging (`_sources.yml` for the `lims`, `assay`, `audit` and `truth` schemas, `stg_*`) and core models: `fct_reportable_result` (`unique` test on sample_id; `<LLOQ` gives an analysis value of 0.5 x assay LLOQ, ADR 003), `missing_results`, `reassay_list` (ABOVE_ULOQ with dilution x 10, DUP_CV, all samples on REJECTED plates). | US-7 (AC-7.1, 7.3, 7.4), US-6 (AC-6.2, 6.4) | `dbt/models/staging/*`, `dbt/models/core/*` | DE-03 to DE-07 |
| DE-09 | `pipeline/run.py`: `build()`, `run_dbt()` (with `--vars` and `PYTHONPATH`), `main()` with `--seed`, `--test`, `--optional-problems`; loads `truth.injected_problems`; calls GXP and LIA functions in the order in DESIGN section 1; writes `docs/results.json` and the README results block (same pattern as clinical-data-review). `tests/conftest.py` with the `built` and `clean_built` fixtures. `tests/test_outputs.py`: raw rows tie out to staging; every sample is either in `fct_reportable_result` or `missing_results`, never both. | US-12 (AC-12.1, 12.2), US-7 (AC-7.4) | `pipeline/run.py`, `tests/conftest.py`, `tests/test_outputs.py` | everything in Phase 1 |
| DE-10 (stretch, D5) | INJ-9 (aliquot with 4 freeze-thaws) and INJ-10 (null performed_by), behind `--optional-problems`. | SPEC section 5 optional | `generator/generate.py` | DE-02 |

## gxp-validation-engineer (GXP)

| ID | Task | Stories / ACs | Owns (files) | Needs |
|---|---|---|---|---|
| GXP-01 | `pipeline/audit.py`: `init_audit`, `insert_records` (batch insert, data and audit rows in one transaction), `correct_record`, `update`/`delete` that raise `AppendOnlyError`, hash chain, `verify_chain`. Tests on in-memory DuckDB: an insert writes N audit rows; `update()` raises; a clean chain is OK; a direct SQL UPDATE on row k makes `first_broken_seq == k`; a correction points to the row it supersedes. **Deliver this first: DE-03 is waiting for it.** | US-3 (AC-3.1 to 3.3) | `pipeline/audit.py`, `tests/test_audit.py` | DE-01 (or none: it can start with only duckdb + pandas) |
| GXP-02 | Validation plan and URS in `docs/validation/`: a demo GAMP 5 / CSA risk-based plan, user requirements traced to US/AC IDs, and the ALCOA+ control matrix (which control covers which attribute). Mark everything as a demo, not a validated system. Include the DuckDB append-only limitation (ADR 001). | US-3, SPEC FAQ | `docs/validation/*` | SPEC, DESIGN |
| GXP-03 | `generator/tamper.py` (`tamper_audit_row`) and `pipeline/integrity.py` (`write_chain_verify`, `rehash_raw_files`). Test: tamper followed by verify catches it at the right record_key. | US-3 (AC-3.3, 3.4 Original), INJ-7 | `generator/tamper.py`, `pipeline/integrity.py` | GXP-01 |
| GXP-04 | dbt integrity models: `v_custody_status`, `custody_flags` (CUSTODY_GAP naming the missing step, CUSTODY_ORDER using the first occurrence of each step, FREEZE_THAW_EXCEEDED), with step order and limits from dbt vars. Tests in `tests/test_custody.py` on `built`: INJ-3 flagged with `received` missing; clean data gives 0 custody flags. | US-2 (AC-2.2 to 2.5), INJ-3 | `dbt/models/integrity/v_custody_status.sql`, `custody_flags.sql`, `_integrity.yml`, `tests/test_custody.py` | DE-08 staging (until then, build against hand-made fixture tables with the contract columns) |
| GXP-05 | dbt `alcoa_findings`: Attributable (performed_by null or not in `lims.users`), Contemporaneous (LATE_ENTRY, more than `late_entry_hours`), Original (HASH_MISMATCH from `audit.file_integrity`), Complete (CUSTODY_GAP). Tests: INJ-4 gives LATE_ENTRY; making a copied raw file writable and editing it in a tmp build gives HASH_MISMATCH. | US-3 (AC-3.4, 3.5), INJ-4 | `dbt/models/integrity/alcoa_findings.sql`, `tests/test_alcoa.py` | GXP-03, DE-08 |
| GXP-06 | Run a full build and check that the audit trail covers every base table: the count of audit INSERT rows per table equals that table's row count. Add this as a test. | US-3 (AC-3.1) | `tests/test_audit.py` | DE-09 |
| GXP-07 | Finish the validation pack after QA: a traceability matrix (requirement to test ID to result) filled with the real pytest and dbt output, the audit-trail review record, and known limitations. | US-3, US-12 | `docs/validation/*` | QA-02 |
| GXP-08 (stretch, D5) | Make sure INJ-9 and INJ-10 are caught by custody_flags and alcoa_findings. | SPEC section 5 optional | integrity models | DE-10 |

## analytics-engineer: Lab Informatics Analyst (LIA)

| ID | Task | Stories / ACs | Owns (files) | Needs |
|---|---|---|---|---|
| LIA-01 | `pipeline/stats.py`: `gmt_ci`, `gmfr_ci`, `clopper_pearson`, `is_seroresponder` (ADR 003). `tests/test_stats.py`: a hand-calculated 5-subject GMT and GMFR to 3 significant figures (show the working in a comment), seroresponse boundaries (exactly 4x; baseline exactly at LLOQ), Clopper-Pearson for 0/n and n/n. | US-8 (AC-8.4) | `pipeline/stats.py`, `tests/test_stats.py` | nothing |
| LIA-02 | `docs/METRICS.md`: a definition for every KPI and immunogenicity metric (formula, numerator, denominator, filters, units, edge cases). Say which LLOQ is used (ADR 003) and that DUP_CV is on OD (ADR 004). Define the ALCOA+ findings-per-100-records denominator. | US-9 (AC-9.2), US-8 | `docs/METRICS.md` | DESIGN |
| LIA-03 | `docs/DASHBOARD_SPEC.md` for Power BI (D4): 3 pages as in AC-11.1. Each visual names its source file in `data/marts/`, fields, filters and DAX. | US-11 (AC-11.1, 11.2) | `docs/DASHBOARD_SPEC.md` | DESIGN section 3 |
| LIA-04 | dbt marts: `mart_immunogenicity.py` (dbt Python model importing `pipeline.stats`; one row per group x visit), `mart_lab_kpis.sql` (long format), `mart_plate_qc.sql`, `_marts.yml` with unique/not_null tests. | US-8 (AC-8.1 to 8.3), US-9 (AC-9.1) | `dbt/models/marts/*` (except the scorecard files) | DE-08 (until then, fixture tables) |
| LIA-05 | `detection_scorecard.sql` and `scorecard_false_positives.sql`: union the flag sources into `(flag_code, key_type, key)` as in DESIGN 3.3, join to `truth.injected_problems`, use `expected_flags` from the dbt vars. `tests/test_scorecard.py`: 100% recall for INJ-1 to INJ-8 (fails and names any miss); FP% reported and at most `max_unexplained_flag_pct`. | US-10 (AC-10.1 to 10.3) | `dbt/models/marts/detection_scorecard.sql`, `scorecard_false_positives.sql`, `tests/test_scorecard.py` | DE-06, GXP-03 to GXP-05 |
| LIA-06 | `pipeline/export.py` (marts and the DESIGN section 8 tables to `data/marts/` as CSV and Parquet via DuckDB COPY) and `pipeline/charts.py` (matplotlib PNGs in `docs/img/`: GMT bar chart with CI bars, one plate's 4PL curve with its standards, plate status grid). | US-11 (AC-11.3, 11.4) | `pipeline/export.py`, `pipeline/charts.py` | LIA-04 |
| LIA-07 | `tests/test_kpis.py`: recompute every KPI from base tables in pandas and match `mart_lab_kpis` (AC-9.3); Vaccine D29 seroresponse > Placebo D29 (AC-8.5); GMFR uses only subjects with both visits (AC-8.2). | US-8 (AC-8.2, 8.5), US-9 (AC-9.3) | `tests/test_kpis.py` | DE-09 |

## tech-lead (TL)

| ID | Task | Stories | Notes |
|---|---|---|---|
| TL-01 | Code review of each seat's diff after Phase 1 and Phase 2: correctness first, then needless complexity, then missing tests. Approve any contract change in DESIGN.md. | all | Findings go in HANDOFF.md |

## qa-engineer (QA)

| ID | Task | Stories | Owns |
|---|---|---|---|
| QA-01 | `docs/team/TEST_PLAN.md` mapping every AC to a pytest or dbt test ID. Note any AC that has no test. | all | TEST_PLAN.md |
| QA-02 | Edge tests: empty plate file, all-blank plate, a plate where every standard fails, a sample with only one well, seeds 1/2/3 still give 100% recall and FP <= 5%, a re-run on an existing `data/` folder (read-only files, R6). Log defects in BUGS.md. | US-4, US-5, US-6, US-10, US-12 | `tests/test_edge_*.py`, `docs/team/BUGS.md` |

## devops-engineer (OPS, light duty)

| ID | Task | Stories | Owns |
|---|---|---|---|
| OPS-01 | Pin `requirements.txt` to the installed versions; `Makefile`; README quickstart for Windows (`.venv\Scripts\python -m pipeline.run --test`); check it runs in under 5 minutes and makes no network calls at runtime. | US-12 (AC-12.1, 12.3) | `requirements.txt` (pinning only), `Makefile`, `README.md` |

## Story coverage

| Story | Tasks |
|---|---|
| US-1 Generator + manifest | DE-02, DE-10 |
| US-2 LIMS + custody | DE-03, GXP-04, GXP-08 |
| US-3 Audit trail + ALCOA+ | GXP-01, GXP-03, GXP-05, GXP-06, DE-03, DE-04, GXP-02, GXP-07 |
| US-4 Ingestion + plate map | DE-04 |
| US-5 4PL + back-calculation | DE-05 |
| US-6 QC + accept/reject | DE-06, DE-08 |
| US-7 Reportable results | DE-07, DE-08, DE-09 |
| US-8 Immunogenicity | LIA-01, LIA-02, LIA-04, LIA-07 |
| US-9 Lab KPIs | LIA-02, LIA-04, LIA-07 |
| US-10 Detection scorecard | LIA-05, QA-02 |
| US-11 Dashboard spec + exports + PNGs | LIA-03, LIA-06 |
| US-12 One command + tests | DE-01, DE-09, OPS-01, QA-01, QA-02 |

Every injected problem has a detecting task: INJ-1, INJ-5, INJ-6, INJ-8 in DE-06; INJ-2 in DE-04; INJ-3 in GXP-04;
INJ-4 in GXP-05; INJ-7 in GXP-03. All of them are scored in LIA-05.
