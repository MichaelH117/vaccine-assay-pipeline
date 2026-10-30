# DESIGN: vaccine-assay-pipeline

Owner: Tech Lead seat. Status: v1.1, 2026-10-29 (contract changes approved after build, see section 10). Input: SPEC.md (US-1 to US-12, INJ-1 to INJ-8).
Decisions taken by the Engineering Manager (Michael can override): D1 DuckDB, D2 ELISA IgG in AU/mL (reported as GMT/GMC),
D3 the spec's default seroresponse rule, D4 Power BI, D5 optional planted problems only if time allows.
All data is synthetic.

ADRs: [001 DuckDB + append-only by API](adr/001-duckdb-append-only-by-api.md),
[002 ELISA concentrations](adr/002-elisa-concentration-gmt-gmc.md),
[003 Seroresponse and LLOQ](adr/003-seroresponse-and-lloq.md),
[004 4PL fit method](adr/004-4pl-fit-method.md),
[005 Where each computation lives](adr/005-python-vs-dbt-split.md),
[006 Repeat runs and reportable selection](adr/006-repeat-runs-and-reportable-selection.md).

---

## 1. Architecture sketch

Same shape as `clinical-data-review`: a seeded generator, a `pipeline` package with one entry point, one DuckDB file,
a dbt project for SQL models and tests, pytest in `tests/`, and a project-local `.venv`.

```
generator/generate.py ──> data/landing/            (CSV: users, subjects, samples, aliquots, custody_events,
   (seeded, writes                                   plate_runs, plate_map, plates/PLATE-NNN.csv,
    answer key)                                      injected_problems.csv)
          │
          ▼  python -m pipeline.run [--seed 42] [--test]
 ┌────────────────────────────── Python (assay math, writes, integrity) ──────────────────────────────┐
 │ 1 lims_load   landing CSV -> lims.*            every insert through audit.insert_records()       │
 │ 2 ingest      plate CSV -> data/raw/ (read-only) + sha256 -> lims.raw_files; parse 8x12 ->       │
 │               assay.well_reads; plate map join; blank correction; ID_MISMATCH -> assay.qc_flags  │
 │ 3 curve       4PL per plate (scipy curve_fit) -> assay.curve_fits, assay.std_recovery,           │
 │               assay.sample_results, assay.control_results                                        │
 │ 4 qc          plate + sample rules -> assay.qc_flags, assay.plate_status                         │
 │ 5 reportable  latest valid run per sample -> assay.reportable_selection (audited, with reason)   │
 │ 6 tamper      INJ-7 only: direct SQL UPDATE of one audit_log row (bypasses the API on purpose)   │
 │ 7 integrity   verify hash chain -> audit.chain_verify; re-hash raw files -> audit.file_integrity │
 │ 8 truth       injected_problems.csv -> truth.injected_problems (read only by scorecard + tests)  │
 └───────────────────────────────────────────────────────────────────────────────────────────────────┘
          │
          ▼  dbt build  (--vars from config/qc_rules.yaml)
   staging (views) ─> integrity (custody, ALCOA+) ─> core (reportable, missing, re-assay) ─> marts
          │
          ▼  Python
 9 export   marts -> data/marts/*.csv + *.parquet (Power BI import, via DuckDB COPY)
10 charts   docs/img/*.png (GMT bars, one plate's 4PL curve, plate status grid)
11 results  docs/results.json + README results block; --test also runs pytest
```

One DuckDB file: `data/warehouse/vaccine_assay.duckdb` (not `assay.duckdb`: DuckDB names the catalog after the
file, which would clash with schema `assay`). It is deleted and rebuilt on every run. No server, no network.

## 2. Folder layout and file ownership

`DE` = data-engineer, `LIA` = analytics-engineer (Lab Informatics Analyst), `GXP` = gxp-validation-engineer,
`QA` = qa-engineer, `OPS` = devops-engineer, `TL` = tech-lead. A seat edits only the files it owns. If you need a change
in someone else's file, ask them in HANDOFF.md or through the Engineering Manager.

```
vaccine-assay-pipeline/
  .venv/                                  local, not committed (OPS sets up; DE may create it on day 1)
  .gitignore                              DE (copy from clinical-data-review; also ignore data/)
  requirements.txt                        DE creates; OPS pins final versions
  pyproject.toml                          DE (pytest pythonpath ".", ruff line-length 120, like clinical-data-review)
  Makefile                                OPS
  README.md                               OPS (results block written by pipeline.run, like clinical-data-review)
  config/qc_rules.yaml                    DE creates with ALL keys from section 5; values change only via a TL-reviewed PR
  generator/__init__.py, generate.py      DE
  generator/tamper.py                     GXP   (INJ-7: direct UPDATE of one audit_log row)
  pipeline/__init__.py                    DE
  pipeline/run.py                         DE    (entry point; wires everyone's functions; `build()` used by conftest)
  pipeline/config.py                      DE    (paths + load_rules())
  pipeline/schema.py                      DE    (DDL for lims.* and assay.* tables)
  pipeline/lims_load.py                   DE
  pipeline/ingest.py                      DE
  pipeline/curve.py                       DE    (4PL, inverse, LLOQ/ULOQ)
  pipeline/qc.py                          DE
  pipeline/reportable.py                  DE
  pipeline/audit.py                       GXP   (DDL for audit.*, write API, hash chain, verify)
  pipeline/integrity.py                   GXP   (raw file re-hash, write chain_verify)
  pipeline/stats.py                       LIA   (GMT/GMFR CIs, Clopper-Pearson, seroresponse: pure functions)
  pipeline/export.py                      LIA   (marts -> data/marts CSV + Parquet)
  pipeline/charts.py                      LIA   (matplotlib PNGs -> docs/img/)
  dbt/dbt_project.yml, profiles.yml       DE
  dbt/macros/generate_schema_name.sql     DE    (copy from clinical-data-review)
  dbt/models/staging/                     DE    (_sources.yml, _staging.yml, stg_*.sql)
  dbt/models/integrity/                   GXP   (v_custody_status, custody_flags, alcoa_findings, _integrity.yml)
  dbt/models/core/                        DE    (fct_reportable_result, missing_results, reassay_list, _core.yml)
  dbt/models/marts/                       LIA   (mart_immunogenicity.py, mart_lab_kpis, mart_plate_qc,
                                                 detection_scorecard, _marts.yml)
  tests/conftest.py                       DE    (session fixtures `built` and `clean_built`, see section 6)
  tests/test_generator.py, test_ingest.py, test_curve.py, test_qc.py, test_reportable.py, test_outputs.py   DE
  tests/test_audit.py, test_custody.py, test_alcoa.py                                                       GXP
  tests/test_stats.py, test_kpis.py, test_scorecard.py                                                      LIA
  tests/test_edge_*.py                                                                                      QA
  docs/METRICS.md, docs/DASHBOARD_SPEC.md, docs/img/                                                         LIA
  docs/validation/                        GXP
  docs/team/DESIGN.md, TASKS.md, adr/     TL
  docs/team/TEST_PLAN.md, BUGS.md         QA
  data/landing/   generator output (rebuilt)       data/raw/   read-only plate CSV copies (AC-3.5)
  data/warehouse/vaccine_assay.duckdb              data/marts/ Power BI exports
```

The only shared-write files are `pipeline/run.py`, `tests/conftest.py`, `requirements.txt` and `config/qc_rules.yaml`.
DE owns all four. Other seats deliver functions with the signatures in section 4, and DE wires them in.

## 3. Data model (the table contracts)

Schemas: `lims`, `assay`, `audit`, `truth` are written by Python. `staging`, `integrity`, `core`, `marts` are built by dbt.
Timestamps are `TIMESTAMP` in UTC with no time zone. IDs are `VARCHAR`. Column names below are the contract: add columns
if you need them, but do not rename or drop these without a TL-approved DESIGN change.

### 3.1 Generator output (`data/landing/`, DE writes, all seats read)

| File | Columns |
|---|---|
| users.csv | user_id (`USR-01`), display_name (`Lab Tech 01`, never a real name), role (`TECH`, `ANALYST`, `QA`), active |
| subjects.csv | subject_id (`SUBJ-0001`), group_name (`Vaccine` or `Placebo`), site_id (`SITE-01`) |
| samples.csv | sample_id (`SMP-00001`), subject_id, visit (`D1`, `D29`, `D57`), visit_day (1, 29, 57), collected_at |
| aliquots.csv | aliquot_id (`ALQ-00001-1`), sample_id, created_at, freeze_thaw_count |
| custody_events.csv | event_id (`EVT-000001`), sample_id, aliquot_id (null before aliquoting), step, performed_by, performed_at, recorded_at, location, plate_id (assayed only), well (assayed only: first well of the duplicate pair), reason |
| plate_runs.csv | plate_id (`PLATE-001`), run_at, analyst, repeat_of_plate_id (null for first runs) |
| plate_map.csv | plate_id, well (`A1`..`H12`), well_type (`STD`, `BLANK`, `CTRL_HIGH`, `CTRL_LOW`, `SAMPLE`), level (std 1-8 or null), nominal_conc (AU/mL, standards only), sample_id, dilution (samples only, default 100) |
| plates/PLATE-NNN.csv | raw reader file: header `,1,2,...,12`, then 8 rows `A`..`H` with 12 OD values, 3 decimals |
| injected_problems.csv | problem_id (`P-001`), inj_type (`INJ-1`..`INJ-8`, optional `INJ-9` freeze-thaw, `INJ-10` null performed_by), key_type (`plate_id`, `sample_id`, `event_id`, `aliquot_id`), affected_key, description |

Rules:
- One `injected_problems` row per affected key. A problem with two keys (INJ-2 swap) has two rows with the same
  problem_id. A problem is detected only if all of its rows are detected.
- INJ-7 lists the custody `event_id` whose audit row `generator/tamper.py` will edit.
- Byte-identical output for the same seed (AC-1.1): fixed base date (no `now()`), fixed float format, `newline=""`
  / `lineterminator="\n"`, sorted rows.
- Plate layout (SPEC section 3): standards in columns 1-2 (8 levels, 3-fold from 1000 AU/mL), blanks, 2 controls in
  duplicate, 37 samples in duplicate in adjacent wells. DE writes the exact well map in a docstring in `generate.py`.
- The generator pre-simulates repeat runs (ADR 006): it writes repeat plates for the samples on INJ-1 and INJ-5 plates,
  for INJ-6 and INJ-8 samples (INJ-8 at the higher dilution). INJ-2 swapped samples are left unresolved on purpose so
  that AC-7.4 (missing_results) has something to show.

### 3.2 Python-written tables

`lims` (DE, via the audit API): `users`, `subjects`, `samples`, `aliquots`, `custody_events`, `plate_runs` (same
columns as the CSVs), plus `raw_files(file_name, plate_id, raw_path, sha256, ingested_at)`.

`assay` (DE, via the audit API):

| Table | Grain | Columns |
|---|---|---|
| plate_map | plate x well | as in the CSV |
| well_reads | plate x well | plate_id, well, row_letter, col_num, od, od_blank_corrected |
| ingest_errors | bad file | file_name, error, logged_at (not audited: it holds no result) |
| curve_fits | plate | plate_id, a, b, c, d, r_squared, converged (bool), fit_message, n_points, lloq_conc, uloq_conc (curve units, before dilution), lloq_od, uloq_od |
| std_recovery | plate x level | plate_id, level, nominal_conc, mean_od, back_calc_conc, recovery_pct, within_limits (bool) |
| control_results | plate x control | plate_id, ctrl_level (`HIGH`, `LOW`), mean_conc, target_conc, low_limit, high_limit |
| sample_results | plate x sample | result_id (`PLATE-001:SMP-00001`), plate_id, sample_id, dilution, mean_od, od_cv_pct, range_flag (`IN_RANGE`, `<LLOQ`, `>ULOQ`; null when the plate has no converged curve or no working range), conc_au_ml (dilution applied; null unless IN_RANGE), run_at |
| qc_flags | flag | flag_id (`RULE:PLATE:KEY`, KEY = sample_id for sample flags, ctrl_level for CTRL_OOR, `-` for other plate flags), level (`PLATE`, `SAMPLE`), plate_id, sample_id (null for plate flags), rule_id (`FIT_FAIL`, `STD_RECOVERY`, `CTRL_OOR`, `BLANK_HIGH`, `DUP_CV`, `BELOW_LLOQ`, `ABOVE_ULOQ`, `ID_MISMATCH`), rule_version, measured_value (DOUBLE), threshold (VARCHAR, e.g. `>=0.98`), blocking (bool), message |
| plate_status | plate | plate_id, status (`ACCEPTED`, `REJECTED`), reject_reasons (comma list of rule_ids, empty if accepted), run_at |
| reportable_selection | LIMS sample (one row per `lims.samples` row) | sample_id, result_id (null if none), decision (`REPORTABLE`, `NO_VALID_RESULT`), reason, n_runs |

Blocking flags: every plate-level flag (via REJECTED), plus `DUP_CV`, `ABOVE_ULOQ`, `ID_MISMATCH`. `BELOW_LLOQ` is not
blocking (the result is reportable as `<LLOQ`). `DUP_CV` and `ID_MISMATCH` are raised on every plate. `BELOW_LLOQ` and
`ABOVE_ULOQ` are raised on ACCEPTED plates only: a rejected plate's curve is not trusted, and all its samples are on the
re-assay list anyway (consequence: a sample that is >ULOQ on a rejected plate is re-assayed at the same dilution).

Audit actor: every pipeline write is audited with `performed_by = 'SYS-PIPELINE'`. It is a system account, not a row in
`lims.users`. The person who did a custody step stays in `custody_events.performed_by`. Any future ALCOA check on
`audit_log.performed_by` must allow `SYS-PIPELINE`.

`audit` (GXP):

| Table | Columns |
|---|---|
| audit_log | audit_seq (BIGINT, 1..n, gap-free), table_name, record_key (key values joined with `|`), action (`INSERT`, `CORRECTION`), field (`*` for an insert), old_value, new_value (canonical JSON of the record for an insert), performed_by, reason, audit_ts_utc, supersedes_seq (null unless a correction), prev_hash, row_hash |
| chain_verify | verified_at, ok (bool), rows_checked, first_broken_seq, broken_table_name, broken_record_key |
| file_integrity | file_name, plate_id, stored_sha256, current_sha256, matches (bool), checked_at (dbt reads the latest check per file) |

Hash rule: `row_hash = sha256(prev_hash + "|" + canonical content)`, where the canonical content is the other columns
(except the hashes) as JSON with sorted keys and ISO timestamps. The first row has `prev_hash = "0" * 64`.

`truth.injected_problems` (DE loads it in `run.py`): same columns as the CSV. Only `marts.detection_scorecard` and
tests may read it. QC, integrity and core logic must never read it.

### 3.3 dbt models

| Model | Owner | Grain | Key columns |
|---|---|---|---|
| staging.stg_* | DE | 1:1 with each source | typed, renamed only, no logic |
| integrity.v_custody_status | GXP | sample | sample_id, current_step, custody_complete (bool), missing_steps (comma list) |
| integrity.custody_flags | GXP | flag | flag_code (`CUSTODY_GAP`, `CUSTODY_ORDER`, `FREEZE_THAW_EXCEEDED`), key_type, key, detail |
| integrity.alcoa_findings | GXP | finding | finding_id, rule_id (e.g. `ALCOA-A1`), attribute (`Attributable`, `Contemporaneous`, `Original`, `Complete`), flag_code (`NO_PERFORMER`, `UNKNOWN_USER`, `LATE_ENTRY`, `HASH_MISMATCH`, `CUSTODY_GAP`), key_type, key, detail |
| core.fct_reportable_result | DE | sample (unique) | sample_id, subject_id, group_name, visit, visit_day, result_id, plate_id, run_at, dilution, reported_value (`<LLOQ` or number as text), conc_au_ml, analysis_value_au_ml, below_lloq (bool), selection_reason |
| core.missing_results | DE | sample | sample_id, subject_id, visit, reason, detail, n_runs |
| core.reassay_list | DE | sample x plate | sample_id, plate_id, rule_id, suggested_dilution, resolved (bool) |
| marts.mart_immunogenicity | LIA | group x visit | group_visit_key, group_name, visit, visit_day, n, gmt, gmt_lcl, gmt_ucl, gmfr, gmfr_lcl, gmfr_ucl, gmfr_n, sero_n (responders), sero_total (paired subjects; was `sero_N`, which collides with `sero_n` in DuckDB), sero_pct, sero_lcl, sero_ucl (GMFR and sero columns null for D1) |
| marts.mart_lab_kpis | LIA | KPI (long format) | kpi_id, kpi_name, value, unit, numerator, denominator |
| marts.mart_plate_qc | LIA | plate | plate_id, status, reject_reasons, run_at, repeat_of_plate_id, converged, r_squared, std_pass_pct, ctrl_high_conc, ctrl_low_conc, mean_blank_od, lloq_conc, uloq_conc, fit_a, fit_b, fit_c, fit_d |
| marts.detection_scorecard | LIA | injected key | scorecard_key (`problem_id:affected_key`), problem_id, inj_type, key_type, affected_key, description, detected (bool), caught_by (flag_codes), problem_detected (bool, all keys of the problem detected) |
| marts.scorecard_false_positives | LIA | 1 row | samples_total, samples_with_unexplained_flag, fp_pct |

The scorecard unions one shape, `(flag_code, key_type, key)`, from `assay.qc_flags` (key_type `plate_id` for plate
flags, `sample_id` for sample flags), `integrity.custody_flags`, `integrity.alcoa_findings`, and
`audit.chain_verify` (`AUDIT_CHAIN_BROKEN`, key_type `event_id`, key = broken_record_key). The accepted flags for
each INJ type come from `scorecard.expected_flags` in the config.

dbt project name `vaccine_assay_pipeline`, profile env var `VAP_DB_PATH`, schemas used as-is through the copied
`generate_schema_name` macro. Folder configs: staging = view, everything else = table.

## 4. Python interfaces (signatures are the contract)

```python
# pipeline/config.py  (DE)
ROOT: Path; CONFIG_PATH = ROOT / "config" / "qc_rules.yaml"
@dataclass(frozen=True)
class Paths: landing: Path; raw: Path; db: Path; marts: Path; img: Path
def default_paths(root: Path = ROOT) -> Paths
def load_rules(path: Path = CONFIG_PATH) -> dict          # parsed YAML; raises if `version` is missing
def dbt_vars(rules: dict) -> dict                         # the subset passed to dbt as --vars (section 5)

# pipeline/audit.py  (GXP)
class AppendOnlyError(RuntimeError): ...
def init_audit(con) -> None                               # creates schema audit + tables
def insert_records(con, table: str, df: pd.DataFrame, key_cols: list[str],
                   performed_by: str, reason: str) -> int # inserts df into `table` AND one audit row per record,
                                                          # in one transaction; returns rows inserted
def correct_record(con, table: str, key: dict, field: str, new_value, performed_by: str,
                   reason: str) -> int                    # appends a CORRECTION audit row whose supersedes_seq points
                                                          # to the row it replaces; never UPDATEs; returns audit_seq.
                                                          # v1 keeps base tables insert-only, so the audit_log is the
                                                          # record of corrections (no record versioning in v1)
def update(*args, **kwargs) -> NoReturn                   # always raises AppendOnlyError (AC-3.2)
def delete(*args, **kwargs) -> NoReturn                   # always raises AppendOnlyError
@dataclass
class ChainResult: ok: bool; rows_checked: int; first_broken_seq: int | None
                   broken_table_name: str | None; broken_record_key: str | None
def verify_chain(con) -> ChainResult

# pipeline/integrity.py  (GXP)
def write_chain_verify(con, result: ChainResult) -> None  # -> audit.chain_verify
def rehash_raw_files(con, raw_dir: Path) -> int           # -> audit.file_integrity; returns mismatches

# generator/tamper.py  (GXP)
def tamper_audit_row(con, event_id: str) -> int           # direct SQL UPDATE of new_value on that event's audit row;
                                                          # returns the audit_seq it changed

# generator/generate.py  (DE)
def generate(seed: int = 42, inject: bool = True, optional_problems: bool = False) -> Study   # dataclass of DataFrames + plate grids
def write(study: Study, landing: Path) -> dict[str, int]  # row counts per file

# pipeline/lims_load.py, ingest.py, curve.py, qc.py, reportable.py  (DE)
def load_lims(con, landing: Path) -> dict[str, int]
def parse_plate_csv(path: Path, plate_id: str) -> pd.DataFrame      # 96 rows or raises PlateFormatError
def ingest_plates(con, landing: Path, raw: Path, rules: dict) -> dict  # copies, hashes, parses, joins, ID_MISMATCH
def four_pl(x, a, b, c, d) -> np.ndarray
def inverse_four_pl(y, a, b, c, d) -> np.ndarray
def fit_plate(std: pd.DataFrame, rules: dict) -> FitResult          # pure, unit-testable
def fit_all(con, rules: dict) -> int
def run_qc(con, rules: dict) -> dict[str, int]
def select_reportable(con) -> int

# pipeline/run.py  (DE)
def build(root: Path, seed: int = 42, inject: bool = True, run_tamper: bool = True) -> Paths  # steps 1-8 + dbt
def run_dbt(db: Path, vars: dict) -> dict                 # same as clinical-data-review, plus --vars and PYTHONPATH=ROOT
def main() -> None                                        # argparse: --seed, --test, --optional-problems

# pipeline/stats.py  (LIA) pure functions on numpy arrays, no DB
def gmt_ci(values, conf: float = 0.95) -> tuple[float, float, float]           # (gmt, lcl, ucl), t-based on log10
def gmfr_ci(post, base, conf: float = 0.95) -> tuple[float, float, float]
def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]
def is_seroresponder(base, post, lloq: float, fold: float = 4.0) -> np.ndarray  # ADR 003

# pipeline/export.py, charts.py  (LIA)
def export_marts(con, out: Path) -> dict[str, int]       # CSV + Parquet via DuckDB COPY
def render_charts(con, out: Path) -> list[Path]          # >= 3 PNGs
```

`run.py` calls `tamper_audit_row` only when `inject=True` and INJ-7 is in the manifest, after all audited writes and
before `verify_chain`.

## 5. The config file: `config/qc_rules.yaml`

One file, one `version` string. Python reads it directly. dbt receives the keys marked (dbt) as `--vars`.
DE creates it on day 1 with these keys and defaults. Every threshold comes from SPEC section 4 and is UNVERIFIED
against ICH M10.

```yaml
version: "QC-RULES-1.0"           # (dbt) stamped on every qc_flags row as rule_version
assay:
  name: "Anti-Antigen X IgG ELISA (synthetic)"
  unit: "AU/mL"
  std_levels_au_ml: [1000, 333.3, 111.1, 37.04, 12.35, 4.115, 1.372, 0.4572]
  default_dilution: 100
  reassay_dilution_factor: 10      # ABOVE_ULOQ suggestion = dilution x 10
  assay_lloq_au_ml: 45.72          # (dbt) lowest standard x default dilution; used for reporting (ADR 003)
  lloq_impute_factor: 0.5          # (dbt)
fit:
  maxfev: 10000
  min_r_squared: 0.98              # FIT_FAIL
  recovery_low_pct: 80
  recovery_high_pct: 120
  min_std_pass_fraction: 0.75      # STD_RECOVERY
controls:
  HIGH: {target_au_ml: 300.0, tolerance_pct: 20}   # CTRL_OOR on back-calculated conc (curve units)
  LOW:  {target_au_ml: 10.0,  tolerance_pct: 20}
plate:
  max_mean_blank_od: 0.15          # BLANK_HIGH
sample:
  max_dup_cv_pct: 20               # DUP_CV, on blank-corrected OD (ADR 004)
custody:
  steps: [collected, received, aliquoted, assayed, stored]   # (dbt)
  max_freeze_thaw: 2               # (dbt)
alcoa:
  late_entry_hours: 24             # (dbt)
immunogenicity:
  seroresponse_fold: 4             # (dbt)
  ci_level: 0.95                   # (dbt)
  baseline_visit: "D1"             # (dbt)
scorecard:
  max_unexplained_flag_pct: 5
  expected_flags:
    INJ-1: [FIT_FAIL, STD_RECOVERY]
    INJ-2: [ID_MISMATCH]
    INJ-3: [CUSTODY_GAP]
    INJ-4: [LATE_ENTRY]
    INJ-5: [CTRL_OOR]
    INJ-6: [DUP_CV]
    INJ-7: [AUDIT_CHAIN_BROKEN]
    INJ-8: [ABOVE_ULOQ]
    INJ-9: [FREEZE_THAW_EXCEEDED]
    INJ-10: [NO_PERFORMER]
```

dbt reads `expected_flags` as well; `dbt_vars()` passes it through as a var. A test asserts that `dbt_vars()` returns
every key marked (dbt).

## 6. Test strategy

- Pattern from clinical-data-review: `tests/conftest.py` has a session fixture `built` that calls
  `pipeline.run.build(tmp_path, seed=42, inject=True)` and yields `{"con": read-only connection, "paths": Paths,
  "truth": DataFrame}`, and a fixture `clean_built` with `inject=False`. The repo's `data/` folder is never touched by
  tests.
- Unit tests on pure functions with no DB: `parse_plate_csv`, `four_pl`/`inverse_four_pl`/`fit_plate` (AC-5.2: known
  parameters, no noise, c within 1%), `stats.*` (AC-8.4: hand-calculated 5-subject example), `audit.update` raises
  (AC-3.2), hash chain on an in-memory DuckDB.
- dbt tests: `unique` + `not_null` on every model grain; `accepted_values` on status and flag codes.
- Integration tests on `built`: AC-10.2 (recall 100% for INJ-1..8), AC-8.5, AC-9.3 recompute, AC-1.4 on `clean_built`.
- `python -m pipeline.run --test` runs pytest and writes the counts into README and `docs/results.json`.

## 7. Dependencies

Add only two packages to the clinical-data-review stack: `scipy` (curve_fit, t and beta quantiles) and `matplotlib`
(3 PNGs). PyYAML already comes with dbt-core; list it explicitly anyway. No pyarrow: DuckDB writes Parquet itself.
No LLM, no network at runtime. Python 3.13 on Windows 11, as in clinical-data-review. OPS pins the exact installed
versions.

## 8. Dashboard (D4)

Power BI. `docs/DASHBOARD_SPEC.md` (LIA) names, for each visual, the source table in `data/marts/`, its fields, filters,
and DAX. The exports cover `mart_immunogenicity`, `mart_lab_kpis`, `mart_plate_qc`, `detection_scorecard`,
`fct_reportable_result` (for the reverse cumulative distribution curve), `alcoa_findings`, `v_custody_status`, and
`assay.control_results` (for the Levey-Jennings chart).

## 9. Risks

| # | Risk | Mitigation | Owner |
|---|---|---|---|
| R1 | DuckDB has no triggers or REVOKE, so append-only is only enforced by the API. Direct SQL can still change rows. | Say this plainly (ADR 001). The hash chain is the detective control, and INJ-7 proves it works. The validation pack lists it as a known limitation. | GXP |
| R2 | `curve_fit` fails or finds a bad local minimum, so a good plate is rejected or INJ-1 is not caught reliably. | Bounds, data-driven starting values, catch `RuntimeError` as `converged=False`. Make INJ-1 a gross error (one standard level off by 3x or more), not a subtle one. Unit-test both outcomes. | DE |
| R3 | Natural noise produces too many DUP_CV or STD_RECOVERY flags (above the 5% false-positive target), or a clean plate fails. | Generator well-to-well CV of about 5%. QA checks the false-positive rate on 3 extra seeds. | DE, QA |
| R4 | The dbt Python model (`mart_immunogenicity.py`) imports `pipeline.stats`. This relies on `PYTHONPATH=ROOT` being set by `run_dbt`, which can break on Windows. | `run_dbt` sets it explicitly. Fallback if it is still flaky after 1 hour: copy the 4 functions into the model file and keep `test_stats.py` testing `pipeline.stats` plus a parity test. | LIA, DE |
| R5 | Byte-identical generator output fails on Windows (CRLF, float repr, set ordering). | Rules in 3.1. AC-1.1 test hashes two runs. | DE |
| R6 | Read-only `data/raw/` files block the next run from deleting them on Windows. | `run.py` sets the files writable again before it cleans up (`os.chmod`). Tests use tmp dirs. | DE |
| R7 | The INJ-2 swap is undetectable if the LIMS only records the plate, not the well. | custody `assayed` events carry `plate_id` and `well` (3.1). ID_MISMATCH compares at well level. | DE |
| R8 | With repeat runs, a sample can have two `assayed` events after `stored`, which looks like CUSTODY_ORDER. | The order check uses the first occurrence of each step only (ADR 006). | GXP |
| R9 | Plate-level LLOQ differs from assay-level LLOQ, which confuses imputation and seroresponse. | ADR 003: label `<LLOQ` by plate range, but impute and judge seroresponse with the fixed assay LLOQ. Documented in METRICS.md. | LIA |
| R10 | Two full builds (dirty and clean) in pytest make the suite slow. | Session-scoped fixtures. Budget: under 2 minutes total. | DE, QA |
| R11 | QC thresholds and the seroresponse rule are UNVERIFIED against ICH M10 and real protocols. | All in config, with the version stamped on every flag. README says "demo defaults". | GXP |
| R12 | Audit volume: one audit row per well read, result and event (about 6k rows). Row-by-row inserts are slow in DuckDB. | `insert_records` builds the audit frame in pandas and inserts it in one batch. The hash chain is computed in Python. | GXP |

## 10. Contract changes approved after the Phase 0-2 build (TL, 2026-10-29)

| # | Change | Asked by | Decision |
|---|---|---|---|
| C1 | DB file `data/warehouse/vaccine_assay.duckdb` | DE | Approved. Needed: catalog name `assay` clashed with schema `assay`. |
| C2 | `sero_N` renamed `sero_total` | LIA | Approved. DuckDB identifiers are case-insensitive. |
| C3 | `checked_at` on `audit.file_integrity` | GXP | Approved. Additive; lets dbt pick the latest check per file. |
| C4 | `qc_flags.flag_id` = `RULE:PLATE:KEY` | DE | Approved. Unique because sample_results is one row per plate x sample. |
| C5 | BELOW_LLOQ / ABOVE_ULOQ only on ACCEPTED plates | DE | Approved, with the consequence written in 3.2 (see REVIEW.md F9). |
| C6 | `SYS-PIPELINE` audit actor, not in `lims.users` | DE | Approved as a system account (3.2). |
| C7 | Added columns (3.3 tables above, `reportable_selection` one row per LIMS sample) | DE, LIA | Approved. All additive. |
