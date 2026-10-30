# METRICS: vaccine-assay-pipeline

Owner: Lab Informatics Analyst (analytics-engineer seat). Status: v1, 2026-10-29. All data is synthetic.
Every threshold below comes from `config/qc_rules.yaml` (version stamped on every QC flag). Values marked "demo
default" are UNVERIFIED against ICH M10 or any real protocol.

Each metric lists: business question, formula, numerator and denominator, grain, filters, unit, edge cases, source
model, and the test that proves it reconciles to the source.

## 0. Shared rules

| Rule | Definition | Source |
|---|---|---|
| Assay | Anti-Antigen X IgG ELISA (synthetic). Results are concentrations in AU/mL. Summaries are labelled **GMT/GMC (AU/mL)** (ADR 002). | config `assay` |
| Analysis value | `conc_au_ml` (back-calculated concentration x dilution) for in-range results. Results reported `<LLOQ` get **0.5 x assay LLOQ** = 0.5 x 45.72 = **22.86 AU/mL**. | `core.fct_reportable_result.analysis_value_au_ml` |
| Which LLOQ | **The fixed assay LLOQ** `assay_lloq_au_ml` = lowest standard x default dilution = 0.4572 x 100 = **45.72 AU/mL**. It is used for imputation and the seroresponse rule. The per-plate working range (LLOQ/ULOQ in curve units) only decides the `<LLOQ` / `>ULOQ` labels (ADR 003, risk R9). | config `assay.assay_lloq_au_ml` |
| Reportable result | Exactly one per sample: the latest run on an ACCEPTED plate with no blocking flag (ADR 006). Samples with none are in `core.missing_results` and are excluded from every statistic below. | `core.fct_reportable_result` |
| Baseline | Visit `D1` (config `immunogenicity.baseline_visit`). | config |
| Confidence level | 95% (config `immunogenicity.ci_level`). | config |
| DUP_CV | Coefficient of variation of the **blank-corrected OD** of the two duplicate wells, not of concentration (ADR 004): `CV% = 100 x SD(od1, od2) / mean(od1, od2)`, SD with n-1. Limit 20% (demo default). | `assay.qc_flags` |

## 1. Immunogenicity metrics (`marts.mart_immunogenicity`, grain: group x visit)

Business question: **Does the vaccine raise antibody levels, and by how much compared with placebo?**
Implemented in `pipeline/stats.py`, called by the dbt Python model `mart_immunogenicity.py`.

### 1.1 GMT/GMC with 95% CI (`gmt`, `gmt_lcl`, `gmt_ucl`, `n`)
- **Formula:** `x_i = log10(analysis_value_i)`. `GMT = 10^mean(x)`. `CI = 10^(mean(x) +/- t(1 - alpha/2, n - 1) x SD(x) / sqrt(n))`, SD with n-1.
- **n:** subjects in the group with a reportable result at that visit.
- **Filters:** reportable results only; analysis value not null.
- **Unit:** AU/mL.
- **Edge cases:** n = 1 gives a GMT with null CI limits (no degrees of freedom). n = 0 gives no row. All values imputed (e.g. placebo baseline) gives GMT = 22.86 with a zero-width CI. Values must be > 0 (imputation guarantees it).
- **Proof:** `tests/test_stats.py::test_gmt_hand_calculated_5_subjects` (values 10, 100, 1000, 100, 100 give GMT 100, CI 13.2 to 755, working in the test comment).

### 1.2 GMFR with 95% CI (`gmfr`, `gmfr_lcl`, `gmfr_ucl`, `gmfr_n`)
- **Formula:** for each subject with **both** a baseline and a post-visit reportable result, `r_i = post_i / base_i`. `GMFR = 10^mean(log10 r)`, with the same t-based CI as 1.1.
- **Denominator (`gmfr_n`):** subjects with both values (AC-8.2). Subjects missing either visit are excluded, so `gmfr_n` can be less than `n`.
- **Filters:** post visits only (`D29`, `D57`). Null on the baseline row.
- **Unit:** ratio (fold rise, no unit).
- **Proof:** `tests/test_stats.py::test_gmfr_hand_calculated_5_subjects` (fold rises 8, 8, 4, 16, 4 give GMFR 6.96, CI 3.39 to 14.3).

### 1.3 Seroresponse rate with 95% Clopper-Pearson CI (`sero_n`, `sero_total`, `sero_pct`, `sero_lcl`, `sero_ucl`)
- **Rule (in words):** a subject is a seroresponder at a post visit if
  - their baseline is **below the assay LLOQ** (45.72 AU/mL) and the post value is **at least 4 x LLOQ** (182.88 AU/mL), or
  - their baseline is **at or above the LLOQ** and the post value is **at least 4 times the baseline**.
  A baseline exactly at the LLOQ uses the fold-rise rule. "At least" includes exactly 4x. Fold (4) and LLOQ come from config.
- **Formula:** `sero_pct = 100 x sero_n / sero_total`. CI: exact Clopper-Pearson, `lcl = Beta(alpha/2; k, n-k+1)`, `ucl = Beta(1-alpha/2; k+1, n-k)`, with `lcl = 0` when k = 0 and `ucl = 1` when k = n; reported in **percent**.
- **Numerator (`sero_n`):** responders. **Denominator (`sero_total`):** subjects with a reportable result at both baseline and the post visit (same as `gmfr_n`).
- **Unit:** %.
- **Edge cases:** null on the baseline row; `sero_total = 0` gives null %.
- **Proof:** `tests/test_stats.py` seroresponse boundary tests (exactly 4x, just under, baseline exactly at LLOQ) and Clopper-Pearson 0/n, n/n and 5/10.
- **Note:** DESIGN 3.3 called the denominator `sero_N`. DuckDB column names are case-insensitive, so it collides with `sero_n`; the column is `sero_total`.

## 2. Lab KPIs (`marts.mart_lab_kpis`, long format, grain: one row per `kpi_id`)

Business question: **Is the lab fast, is the assay running cleanly, and is the data trustworthy?**
Columns: `kpi_id, kpi_name, value, unit, numerator, denominator`. AC-9.3: `tests/test_kpis.py` (LIA-07, Phase 2)
recomputes each value from base tables in pandas.

| kpi_id | Formula | Numerator | Denominator | Unit | Edge cases |
|---|---|---|---|---|---|
| `TAT_MEDIAN_DAYS` | median over samples of `(run_at of the reportable result - first 'received' custody performed_at) / 86400 s` (continuous quantile) | null | samples with a reportable result and a `received` event | days | samples with no reportable result are excluded (they are in `missing_results`) |
| `TAT_P90_DAYS` | 90th percentile (continuous, linear interpolation) of the same per-sample TAT | null | same | days | as above |
| `PLATE_FAIL_RATE` | `100 x rejected plates / all plates` | plates with `status = 'REJECTED'` | all rows in `assay.plate_status` (repeat plates count as plates) | % | null if no plates |
| `PLATE_REJECT_<RULE>` for FIT_FAIL, STD_RECOVERY, CTRL_OOR, BLANK_HIGH, INGEST_ERROR (unreadable plate file kept as REJECTED) | count of rejected plates whose `reject_reasons` list contains the rule | that count | all plates | plates | one plate with two reasons counts once under each; a row is always present, 0 if none |
| `REASSAY_RATE` | `100 x distinct samples on core.reassay_list / distinct samples with any result in assay.sample_results` | samples on the re-assay list (ABOVE_ULOQ, DUP_CV, or on a REJECTED plate) | samples assayed at least once | % | a sample on several re-assay rows counts once |
| `CUSTODY_COMPLETE_PCT` | `100 x samples with custody_complete / all samples` | `integrity.v_custody_status.custody_complete = true` | all rows in `v_custody_status` (one per sample) | % | |
| `ALCOA_FINDINGS_PER_100` | `100 x ALCOA+ findings / custody event records` | rows in `integrity.alcoa_findings` | **rows in `lims.custody_events`** (the records the Attributable and Contemporaneous checks inspect) | findings per 100 records | HASH_MISMATCH findings (file-level) and CUSTODY_GAP (sample-level) are counted in the numerator too, so this is a rate per 100 custody records, not a strict proportion |

## 3. Plate QC (`marts.mart_plate_qc`, grain: plate)

Business question: **Which plates can be trusted, and why were the others rejected?**

| Column | Definition | Unit |
|---|---|---|
| `status`, `reject_reasons` | from `assay.plate_status`; any plate-level flag means REJECTED | |
| `r_squared` | `1 - SS_res / SS_tot` of the 4PL fit on all 16 standard wells (ADR 004); FIT_FAIL below 0.98 (demo default) | ratio |
| `std_pass_pct` | `100 x standard levels with recovery in 80-120% / standard levels` (STD_RECOVERY below 75% of levels, demo default) | % |
| `ctrl_high_conc`, `ctrl_low_conc` | back-calculated mean control concentration in curve units (targets 300 / 10 AU/mL, +/- 20%) | AU/mL |
| `mean_blank_od` | mean **raw** OD of the BLANK wells (BLANK_HIGH above 0.15, demo default) | OD |
| `lloq_conc`, `uloq_conc` | plate working range in curve units, before dilution | AU/mL |

## 4. Detection scorecard (`marts.detection_scorecard`, `marts.scorecard_false_positives`)

Business question: **Does the pipeline catch every planted problem, without flagging too much clean data?**

- **Flag union:** `(flag_code, key_type, key)` from `assay.qc_flags` (plate flags keyed on `plate_id`, sample flags on
  `sample_id`), `integrity.custody_flags`, `integrity.alcoa_findings`, and `audit.chain_verify` when not ok
  (`AUDIT_CHAIN_BROKEN`, `event_id`, `broken_record_key`).
- **Detected (per injected key):** at least one flag listed for that INJ type in `scorecard.expected_flags` sits on the
  same `key_type` and `key`, **and** the key carries none of that INJ type's masking flags. Masking (REVIEW F3): a
  broken curve also produces CTRL_OOR, so INJ-5 ("control off, curve fine") counts only when its plate has no FIT_FAIL
  or STD_RECOVERY (`masked_by` shows why a key was not credited). Masking lists come from dbt var `masking_flags`
  (default `{INJ-5: [FIT_FAIL, STD_RECOVERY]}`). An INJ type with no `expected_flags` entry is never detected (a loud miss).
- **Counting unit: the problem, not the key** (`marts.scorecard_summary`). A problem (`problem_id`) is detected only
  when all of its keys are detected. INJ-2 (a sample swap) is **one problem with two sample keys**, so seed 42 has
  **12 planted problems on 13 affected records**. The headline always says
  "X of Y required planted problems caught (A of B affected records); C of D optional".
- **Required vs optional:** required = INJ types in dbt var `required_inj_types` (default INJ-1 to INJ-8, AC-10.2);
  recall on them must be 100%. Optional = every other planted type (INJ-9, INJ-10 behind `--optional-problems`, or a
  future GXP injection until it is added to `required_inj_types`). Optional problems get their own counts and are
  never folded into the required recall. With `--optional-problems` on seed 42: 12 of 12 required and 2 of 2 optional.
- **Recall:** `required problems detected / required problems planted`. Target 100%, enforced by
  `tests/test_scorecard.py`.
- **Sample false-positive rate (`fp_pct`):** `100 x samples_with_unexplained_flag / samples_total`.
  - **Sample-level flag:** a **blocking** SAMPLE flag in `assay.qc_flags` (DUP_CV, ABOVE_ULOQ, ID_MISMATCH), or a custody
    or ALCOA+ flag keyed on the sample, one of its aliquots or one of its custody events. `BELOW_LLOQ` is excluded: it
    is a normal result (most placebo baselines), not a problem.
  - **Explained (REVIEW F7):** a (sample, flag code) pair is explained only when an injected key linked to that sample
    (the sample, an aliquot or an event) has an INJ type whose `expected_flags` include that flag code. A natural DUP_CV
    on an INJ-2 or INJ-3 sample is therefore NOT excused. Accepted looseness: a planted sample-level problem explains the
    same flag on any plate that sample ran on (cross-plate match).
  - **Denominator:** all samples in `lims.samples`. Target at most 5% (`scorecard.max_unexplained_flag_pct`), reported
    even when natural noise causes DUP_CV flags (AC-10.3).
- **Plate false-reject rate (`plate_fp_pct`, REVIEW F2):** `100 x plates_rejected_unexplained / plates_total`, where an
  unexplained reject is a REJECTED plate that is not an injected `plate_id` key (`unexplained_plate_ids` lists them).
  Reported separately because one false reject removes about 37 samples from reporting. Seed 42: 0 of 13.
- Only the scorecard models and tests read `truth.injected_problems`.

## 5. Outputs and the question each answers

| Output | Business question |
|---|---|
| `docs/img/gmt_by_group_visit.png` | Does the vaccine group's antibody level rise above placebo after dosing? |
| `docs/img/plate_4pl_curve.png` | Is a typical plate's standard curve a good fit, and what is its working range? |
| `docs/img/plate_status_grid.png` | How many plates passed QC, and which rule failed the others? |
| `data/marts/*.csv`, `*.parquet` | The Power BI import set (see `docs/DASHBOARD_SPEC.md`). |
