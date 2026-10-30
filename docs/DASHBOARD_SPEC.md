# DASHBOARD SPEC: Power BI build (vaccine-assay-pipeline)

Owner: Lab Informatics Analyst. Status: v1, 2026-10-29 (decision D4: Power BI). All data is synthetic.
Audience: clinical immunology lead, lab manager, QA. Metric definitions: `docs/METRICS.md`.

## 0. Data model

Import from `data/marts/` (Get Data > Parquet, or Text/CSV). Every file is rebuilt by `python -m pipeline.run`.

| Table (file stem) | Grain | Business question | Key |
|---|---|---|---|
| `mart_immunogenicity` | group x visit | Does the vaccine raise antibodies? | `group_visit_key` |
| `fct_reportable_result` | sample | Distribution of individual results (RCD curve) | `sample_id` |
| `mart_plate_qc` | plate | Which plates passed QC? | `plate_id` |
| `control_results` | plate x control level | Is the assay drifting? (Levey-Jennings) | `plate_id`, `ctrl_level` |
| `mart_lab_kpis` | KPI | Is the lab fast and clean? | `kpi_id` |
| `v_custody_status` | sample | Where is each sample in its chain of custody? | `sample_id` |
| `alcoa_findings` | finding | Which records break data-integrity rules? | `finding_id` |
| `detection_scorecard` | injected key | Did the pipeline catch every planted problem? | `scorecard_key` |
| `scorecard_false_positives` | 1 row | How much clean data was flagged, and were any plates rejected by mistake? | none |
| `scorecard_summary` | 1 row | How many planted problems were caught? (headline) | none |

Relationships (single direction, one to many):
- `mart_plate_qc[plate_id]` 1 -> * `control_results[plate_id]`
- `mart_plate_qc[plate_id]` 1 -> * `fct_reportable_result[plate_id]`
- `v_custody_status[sample_id]` 1 -> 1 `fct_reportable_result[sample_id]` (both directions off; filter from custody)

Helper tables (DAX calculated tables):

```dax
VisitOrder = DATATABLE("visit", STRING, "visit_day", INTEGER, {{"D1", 1}, {"D29", 29}, {"D57", 57}})

-- log-spaced concentrations for drawing 4PL curves (curve units, AU/mL)
CurveX = SELECTCOLUMNS(GENERATESERIES(-1, 3.3, 0.05), "log_x", [Value], "x", POWER(10, [Value]))
```

Sort `visit` by `visit_day` everywhere (Column tools > Sort by column). Theme: Vaccine = `#2a78d6`, Placebo =
`#eb6834`; status good = `#0ca30c`, critical = `#d03b3b`, always shown with a text label, never color alone.
Page-level filter on every page: none (synthetic study, one assay). Report-level text box: "Synthetic data. QC
thresholds are demo defaults, UNVERIFIED against ICH M10."

---

## Page 1: Immunogenicity

Question: **Does the vaccine raise antibody levels compared with placebo, and in how many subjects?**
Slicer (top row): `mart_immunogenicity[group_name]` (multi-select, default all).

### 1.1 GMT/GMC by group x visit, with 95% CI error bars
- **Visual:** clustered column chart, Y axis log scale.
- **Source:** `mart_immunogenicity`.
- **Fields:** X = `visit` (sorted by `visit_day`); Legend = `group_name`; Y = `[GMT]`; error bars (Analytics pane >
  Error bars, "By field") lower = `[GMT LCL]`, upper = `[GMT UCL]`. Tooltip: `n`, `[GMT label]`.
- **Title:** "GMT/GMC (AU/mL) by group and visit, 95% CI". Y axis title "GMT/GMC (AU/mL, log scale)".
- **DAX:**
```dax
GMT = MAX(mart_immunogenicity[gmt])
GMT LCL = MAX(mart_immunogenicity[gmt_lcl])
GMT UCL = MAX(mart_immunogenicity[gmt_ucl])
GMT label = FORMAT([GMT], "#,0") & " (" & FORMAT([GMT LCL], "#,0") & " to " & FORMAT([GMT UCL], "#,0") & ")"
```
  The mart is already one row per group x visit, so MAX returns the stored value; no re-aggregation of geometric
  means in DAX (averaging GMTs across groups would be wrong).

### 1.2 Reverse cumulative distribution (RCD) curve
- **Visual:** line chart, X axis log scale.
- **Source:** `fct_reportable_result`.
- **Fields:** X = `analysis_value_au_ml` (Don't summarize); Y = `[RCD %]`; Legend = `group_name`; small multiples or
  slicer = `visit` (default D29).
- **Title:** "Reverse cumulative distribution of IgG (AU/mL), by group". Y axis "% of subjects >= value".
- **DAX:**
```dax
RCD % =
VAR v = MAX(fct_reportable_result[analysis_value_au_ml])
VAR grp = SELECTEDVALUE(fct_reportable_result[group_name])
VAR vis = SELECTEDVALUE(fct_reportable_result[visit])
VAR denom = CALCULATE(COUNTROWS(fct_reportable_result),
    ALL(fct_reportable_result), fct_reportable_result[group_name] = grp, fct_reportable_result[visit] = vis)
VAR num = CALCULATE(COUNTROWS(fct_reportable_result),
    ALL(fct_reportable_result), fct_reportable_result[group_name] = grp, fct_reportable_result[visit] = vis,
    fct_reportable_result[analysis_value_au_ml] >= v)
RETURN DIVIDE(num, denom) * 100
```
- **Note:** `<LLOQ` results sit at the imputed 22.86 AU/mL, so the curve has a step there. Add a constant line at
  X = 45.72 labelled "Assay LLOQ".

### 1.3 Seroresponse table
- **Visual:** table (matrix with no subtotals).
- **Source:** `mart_immunogenicity`, filter `visit <> "D1"` (visual-level filter).
- **Columns:** `group_name`, `visit`, `[Seroresponse n/N]`, `[Seroresponse %]`, `[Seroresponse 95% CI]`,
  `[GMFR (95% CI)]`, `gmfr_n`.
- **DAX:**
```dax
Seroresponse n/N = MAX(mart_immunogenicity[sero_n]) & "/" & MAX(mart_immunogenicity[sero_total])
Seroresponse % = MAX(mart_immunogenicity[sero_pct])
Seroresponse 95% CI = FORMAT(MAX(mart_immunogenicity[sero_lcl]), "0.0") & " to "
    & FORMAT(MAX(mart_immunogenicity[sero_ucl]), "0.0") & "%"
GMFR (95% CI) = FORMAT(MAX(mart_immunogenicity[gmfr]), "0.00") & " (" & FORMAT(MAX(mart_immunogenicity[gmfr_lcl]), "0.00")
    & " to " & FORMAT(MAX(mart_immunogenicity[gmfr_ucl]), "0.00") & ")"
```
- **Footnote text:** "Seroresponse: baseline < LLOQ (45.72 AU/mL) and post >= 4 x LLOQ, or baseline >= LLOQ and
  post >= 4 x baseline. N = subjects with both visits. Exact Clopper-Pearson CI."

---

## Page 2: Assay QC

Question: **Which plates can be trusted, and is the assay stable over time?**
Slicer: `mart_plate_qc[status]`.

### 2.1 Plate status grid
- **Visual:** matrix used as a tile grid (or the "Card (new)" visual with one card per plate).
- **Source:** `mart_plate_qc`.
- **Fields:** Rows = `plate_id`; Values = `[Plate status label]`, `reject_reasons`, `r_squared`, `std_pass_pct`.
  Conditional formatting: background of `[Plate status label]` by field value `[Plate status color]`.
- **DAX:**
```dax
Plate status label = IF(MAX(mart_plate_qc[status]) = "ACCEPTED", "ACCEPTED", "REJECTED: " & MAX(mart_plate_qc[reject_reasons]))
Plate status color = IF(MAX(mart_plate_qc[status]) = "ACCEPTED", "#0ca30c", "#d03b3b")
```
- **Static equivalent:** `docs/img/plate_status_grid.png`.

### 2.2 Curve fit gallery
- **Visual:** line chart with small multiples by `mart_plate_qc[plate_id]`, X axis log scale.
- **Source:** `CurveX` (X) and `mart_plate_qc` (parameters). Add a relationship-free cross join through the measure.
- **Fields:** X = `CurveX[x]`; Y = `[4PL OD]`; small multiples = `mart_plate_qc[plate_id]`; tooltip `r_squared`,
  `lloq_conc`, `uloq_conc`. Title "Standard curves by plate (4PL, blank-corrected OD vs AU/mL)".
- **DAX:**
```dax
4PL OD =
VAR x = MAX(CurveX[x])
VAR a = MAX(mart_plate_qc[fit_a]) VAR b = MAX(mart_plate_qc[fit_b])
VAR c = MAX(mart_plate_qc[fit_c]) VAR d = MAX(mart_plate_qc[fit_d])
RETURN IF(ISBLANK(c), BLANK(), d + (a - d) / (1 + POWER(x / c, b)))
```
- Plates whose fit did not converge show an empty panel; the grid (2.1) says FIT_FAIL. Static example of one plate
  with its standard points: `docs/img/plate_4pl_curve.png`.

### 2.3 Levey-Jennings control chart
- **Visual:** line chart with markers, one per control level (small multiples by `ctrl_level`).
- **Source:** `control_results` related to `mart_plate_qc` (for `run_at`).
- **Fields:** X = `mart_plate_qc[run_at]` (then `plate_id` as tie-break in tooltip); Y = `[Control conc]`; constant
  lines from measures `[Control target]`, `[Control low limit]`, `[Control high limit]`, plus `[Mean +/- 2SD]` bands.
  Title "Levey-Jennings: control concentration by run (AU/mL)".
- **DAX:**
```dax
Control conc = AVERAGE(control_results[mean_conc])
Control target = MAX(control_results[target_conc])
Control low limit = MAX(control_results[low_limit])
Control high limit = MAX(control_results[high_limit])
Control mean (level) = CALCULATE(AVERAGE(control_results[mean_conc]), ALLEXCEPT(control_results, control_results[ctrl_level]))
Control SD (level) = CALCULATE(STDEV.S(control_results[mean_conc]), ALLEXCEPT(control_results, control_results[ctrl_level]))
Upper 2SD = [Control mean (level)] + 2 * [Control SD (level)]
Lower 2SD = [Control mean (level)] - 2 * [Control SD (level)]
Out of range = IF([Control conc] < [Control low limit] || [Control conc] > [Control high limit], 1, 0)
```
  Marker color by `[Out of range]` (critical red + tooltip "CTRL_OOR"). The +/-20% limits are the QC rule; the 2SD
  bands are descriptive only.

---

## Page 3: Lab ops and data integrity

Question: **Is the lab fast, is custody complete, and is the record trustworthy?**

### 3.1 KPI cards
- **Visual:** 6 cards in one row.
- **Source:** `mart_lab_kpis`. Each card is the same measure with a visual-level filter on `kpi_id`.
- **Cards:** `TAT_MEDIAN_DAYS` ("Median TAT, days"), `TAT_P90_DAYS` ("P90 TAT, days"), `PLATE_FAIL_RATE`
  ("Plate failure rate %"), `REASSAY_RATE` ("Re-assay rate %"), `CUSTODY_COMPLETE_PCT` ("Complete custody %"),
  `ALCOA_FINDINGS_PER_100` ("ALCOA+ findings per 100 records").
- **DAX:**
```dax
KPI value = MAX(mart_lab_kpis[value])
KPI detail = FORMAT(MAX(mart_lab_kpis[numerator]), "0") & " / " & FORMAT(MAX(mart_lab_kpis[denominator]), "0")
```
  `KPI detail` is the card subtitle (blank for TAT, which has no numerator).
- Bar chart beside the cards: `mart_lab_kpis` filtered to `kpi_id` starting "PLATE_REJECT_", X = `kpi_name`,
  Y = `[KPI value]`, title "Rejected plates by rule".

### 3.2 Custody funnel
- **Visual:** funnel.
- **Source:** `v_custody_status`.
- **Fields:** Category = `[Custody step]` (from a DAX table of the 5 steps in order); Values = `[Samples reached step]`.
  Title "Samples reaching each custody step".
- **DAX:**
```dax
CustodySteps = DATATABLE("step", STRING, "step_order", INTEGER,
    {{"collected", 1}, {"received", 2}, {"aliquoted", 3}, {"assayed", 4}, {"stored", 5}})

Samples reached step =
VAR s = SELECTEDVALUE(CustodySteps[step])
RETURN CALCULATE(COUNTROWS(v_custody_status),
    NOT CONTAINSSTRING("," & v_custody_status[missing_steps] & ",", "," & s & ","))
```
  Sort `step` by `step_order`. Steps follow config `custody.steps`; update `CustodySteps` if that list changes.

### 3.3 ALCOA+ findings table
- **Visual:** table with a slicer on `attribute`.
- **Source:** `alcoa_findings`.
- **Columns:** `finding_id`, `attribute`, `rule_id`, `flag_code`, `key_type`, `key`, `detail`.
- **DAX:** `Findings = COUNTROWS(alcoa_findings)` shown in the slicer header and as a card.

### 3.4 Detection scorecard (demo proof)
- **Visual:** table + two cards.
- **Source:** `detection_scorecard`, `scorecard_false_positives`, `scorecard_summary`.
- **Columns:** `problem_id`, `inj_type`, `affected_key`, `detected`, `caught_by`. Conditional icon on `detected`
  (check / cross with text "Caught" / "Missed").
- **DAX:**
```dax
Headline = MAX(scorecard_summary[headline])
Required recall % = MAX(scorecard_summary[required_recall_pct])
FP % = MAX(scorecard_false_positives[fp_pct])
Plate false rejects = MAX(scorecard_false_positives[plates_rejected_unexplained])
```
  Cards: `[Headline]` (text card, e.g. "12 of 12 required planted problems caught (13 of 13 affected records); 0 of 0
  optional"), "Required recall (%)", "Samples with an unexplained flag (%) - target <= 5%", "Plates rejected without a
  planted cause". The counting unit is the problem, not the table row: do not compute recall as COUNTROWS of
  `detection_scorecard`, which has one row per affected key (METRICS.md section 4).

---

## Acceptance check (AC-11.1, 11.2)

| Page | Visuals | Sources |
|---|---|---|
| Immunogenicity | GMT bar + CI, RCD curve, seroresponse table | `mart_immunogenicity`, `fct_reportable_result` |
| Assay QC | plate status grid, curve fit gallery, Levey-Jennings | `mart_plate_qc`, `control_results` |
| Lab ops and data integrity | KPI cards, custody funnel, ALCOA+ table (+ scorecard) | `mart_lab_kpis`, `v_custody_status`, `alcoa_findings`, `detection_scorecard`, `scorecard_false_positives` |
