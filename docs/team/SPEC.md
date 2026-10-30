# SPEC: vaccine-assay-pipeline

Owner: Product Owner seat. Status: DRAFT v1, waiting for Michael's call on the open decisions (section 8).
Date: 2026-10-29. Hands off to: tech-lead.

All data is synthetic. Nothing here describes or uses real patient or trial data.

---

## 1. PR/FAQ

### Press release (internal, imaginary)

**Synthetic vaccine-trial assay lab gets a full data trail, from blood draw to GMT table, in one command**

*Clinical immunology demo, built by Michael Hanson*

A vaccine trial lives or dies on its immunogenicity data: did the vaccine group make more antibody than placebo? Before that number reaches a statistician, an assay lab has to receive thousands of serum tubes, keep an unbroken chain of custody, run them on 96-well plates, fit a standard curve to every plate, throw out plates that fail QC, and prove that no record was changed without a trace.

`vaccine-assay-pipeline` does that work end to end on synthetic data. A mini-LIMS tracks every serum sample through collected, received, aliquoted, assayed, and stored, writing every event to an append-only audit trail checked against ALCOA+. A Python pipeline reads raw plate-reader CSVs, fits a 4-parameter logistic (4PL) standard curve per plate, back-calculates antibody concentrations, applies plate- and sample-level QC rules, and accepts or rejects each plate. dbt models then produce GMT, GMFR, and seroresponse rates by vaccine group and visit, plus lab KPIs such as turnaround time and plate failure rate.

The data generator plants known problems (a failing plate, swapped sample IDs, a missing custody step, a late audit entry, and more). The pipeline's own scorecard reports how many it caught. "Lab data people spend their days on exactly these problems," said the imaginary lab head. "Seeing them caught automatically, with a reason code, is what I'd want from a pipeline."

Run `python -m pipeline.run` (exact command set by DevOps) and open the dashboard spec.

### FAQ

**Q: Who is this for?** The assay lab's data reviewer in a vaccine-trial clinical immunology lab, the study statistician, and QA / data integrity staff. It covers LIMS data, assay math, GxP data integrity, SQL/dbt, and reporting.

**Q: How is it different from Michael's clinical-data-review project?** That project checks CRF/SDTM clinical data with edit checks. This one sits upstream in the lab: specimens, plates, curves, and assay QC. No SDTM domains, no CRF edit checks. The only shared idea is "inject known problems and measure detection".

**Q: Is this a validated GxP system?** No. It demonstrates GxP-style controls (append-only audit trail, ALCOA+ checks, reason codes, versioned rules) on synthetic data. The GxP Validation Engineer will write a light validation pack, clearly marked as a demo.

**Q: Why 4PL?** Immunoassay (ELISA) standard curves are S-shaped, and the 4PL model is the standard way to fit them and read unknowns back off the curve. ICH M10 lists ligand binding assay calibration curve rules in its section 4.2.3 (https://www.hhs.gov/guidance/sites/default/files/hhs-guidance-documents/FDA/50093493fnl_M10-Bioanalytical-Method-Validation-and-Study-Sample-Analysis_Jan-2025-update.pdf).

**Q: Are the QC thresholds real?** They are realistic defaults kept in one config file so they can be changed. Standard recovery of 80-120% is a common vendor rule (https://conductscience.com/tools/elisa-curve-fitter). The exact M10 numbers were not checked against the PDF: UNVERIFIED.

**Q: Does it use an LLM?** No. No LLM is needed for v1. If one is added later, it must be local Ollama only.

**Q: What does "done" look like?** One command builds the data, the LIMS, the assay results, the dbt marts, and a detection scorecard. Every acceptance criterion below passes in pytest or `dbt test`.

---

## 2. Grounding: terms and sources

| Term | Meaning in this project | Source |
|---|---|---|
| 4PL | y = d + (a - d) / (1 + (x/c)^b). a = response at zero, d = response at infinite concentration, c = inflection point (EC50), b = slope. Unknowns are read back by inverting the curve. | https://www.casrai.org/guides/four-parameter-logistic-elisa-standard-curve-fitting ; https://bitesizebio.com/42883/an-exploration-of-the-sigmoidal-curve-math-for-the-rest-of-us |
| Back-calculation | Run each standard's signal back through the fitted curve and compare it to its nominal concentration (% recovery). A high R² can hide bias at the ends, and back-calculation catches it. | https://www.casrai.org/guides/four-parameter-logistic-elisa-standard-curve-fitting |
| LLOQ / ULOQ | The lowest and highest concentrations where back-calculated accuracy is acceptable. Samples above ULOQ are re-assayed at a higher dilution. | https://conductscience.com/tools/elisa-curve-fitter |
| GMT / GMC | Log-transform titers, average them, and transform back. The 95% CI is built on the log scale. | https://cdn.clinicaltrials.gov/large-docs/99/NCT04650399/SAP_002.pdf |
| GMFR | Geometric mean of each subject's post-dose / baseline ratio. | https://cdn.clinicaltrials.gov/large-docs/76/NCT04405076/SAP_001.pdf |
| Seroresponse | Default: a rise from below LLOQ to at least 4 x LLOQ, or at least a 4-fold rise if baseline is at or above LLOQ. Definitions vary by protocol. | https://cdn.clinicaltrials.gov/large-docs/76/NCT04405076/SAP_001.pdf ; https://cdn.clinicaltrials.gov/large-docs/77/NCT04789577/Prot_000.pdf |
| Below-LLOQ imputation | Results below LLOQ are set to 0.5 x LLOQ before GMT/GMFR. | https://cdn.clinicaltrials.gov/large-docs/77/NCT04789577/Prot_000.pdf |
| GCLP | Good Clinical Laboratory Practice: GLP principles applied to clinical trial sample analysis, covering SOPs, trial material handling and chain of custody, data recording, and repeat analysis. | https://tdr.who.int/publications/i/item/good-clinical-laboratory-practice-(-gclp) |
| ALCOA+ | Attributable, Legible, Contemporaneous, Original, Accurate, plus Complete, Consistent, Enduring, and Available. Audit trails must show who, what, when, and why, and must be reviewed. | https://www.fda.gov/regulatory-information/search-fda-guidance-documents/data-integrity-and-compliance-drug-cgmp-questions-and-answers (URL not opened in this session: UNVERIFIED link) ; https://www.labmanager.com/audit-trails-data-integrity-and-ai-what-regulated-labs-need-to-know-35642 ; https://casrai.org/dictionary/term/alcoa-plus-data-integrity |

The project does not claim any specific LIMS product or assay used by a real lab.

---

## 3. Users and workflow

| User | What they do | What they need from this project |
|---|---|---|
| Sample management tech | Receives serum tubes, checks the manifest, aliquots, and stores in freezers | Custody status per sample. Flags for missing steps, late entries, and freeze-thaw over the limit. |
| Assay scientist / analyst | Builds plate maps, runs ELISA plates, reviews curves | Per-plate 4PL fit, QC flags with reason codes, and accept/reject. A re-assay list (failed plates, above-ULOQ samples). |
| Lab data manager / QA reviewer | Reviews the audit trail, ALCOA+ compliance, and data transfer | Append-only audit log, ALCOA+ check results, and a detection scorecard. |
| Clinical immunology lead / statistician | Consumes reportable results | GMT, GMFR, and seroresponse by group and visit. Lab KPIs. |

Workflow (one sample):
1. Collected at site (synthetic).
2. Received at lab and checked against the shipment manifest.
3. Aliquoted into child tubes.
4. Assayed on plate P, well W.
5. Stored at -80 C.

Each step writes an audit event. Plate CSV gets ingested, then 4PL fit, then QC, then plate accept/reject, then reportable result per sample, then dbt marts, then report and dashboard.

Synthetic study design (default): 2 groups (Vaccine, Placebo), 60 subjects each, 3 visits (Day 1 baseline, Day 29, Day 57). That is 360 serum samples, one ELISA IgG assay with results in AU/mL, about 10-12 plates plus repeats. Fixed random seed.

Plate layout (default): 8-point standard curve in duplicate (16 wells), 2 blanks, high and low positive controls in duplicate (4 wells), and 37 samples in duplicate (74 wells). 96 wells total.

---

## 4. User stories and acceptance criteria

Every QC threshold below lives in one config file (for example `config/qc_rules.yaml`) with a version string. Default numbers are written in brackets.

### US-1: Seeded synthetic data generator with an injected-problem manifest
As an analyst, I want reproducible synthetic trial, LIMS, and plate-reader data with known planted problems, so that detection can be measured.
- AC-1.1: Running the generator twice with the same seed gives byte-identical output files (checked by SHA-256).
- AC-1.2: It writes subjects (subject_id, group, site), samples (sample_id, subject_id, visit, collected_at), custody events, plate maps, and one raw plate-reader CSV per plate in a 96-well layout (rows A-H, columns 1-12, OD values).
- AC-1.3: It writes `injected_problems.csv`, listing every planted problem with problem_id, type, and affected key (plate_id, sample_id, or event_id). It contains at least one of each type INJ-1 to INJ-8 (section 5).
- AC-1.4: Vaccine group Day 29 GMT is at least 4x the baseline GMT. Placebo GMFR is between 0.8 and 1.25. Both are checked on clean data (no injected problems).
- AC-1.5: No real names, MRNs, or dates of birth appear. Subject IDs follow a synthetic pattern (for example `SUBJ-0001`).

### US-2: Mini-LIMS sample registry and chain of custody
As a sample management tech, I want every sample's custody steps recorded in order, so that I can prove where each tube was at all times.
- AC-2.1: Database tables exist for samples, aliquots, and custody_events, in DuckDB by default (see decision D1). custody_events has event_id, sample_id, step, performed_by, performed_at, recorded_at, location, and reason.
- AC-2.2: Allowed steps and order are collected, then received, then aliquoted, then assayed, then stored. A view `v_custody_status` gives each sample's current step and a `custody_complete` flag.
- AC-2.3: A sample with a skipped step (for example aliquoted with no received) is flagged `CUSTODY_GAP`, naming the missing step.
- AC-2.4: A step recorded out of order (performed_at earlier than the previous step) is flagged `CUSTODY_ORDER`.
- AC-2.5: An aliquot with more than [2] freeze-thaw cycles is flagged `FREEZE_THAW_EXCEEDED`.

### US-3: Append-only audit trail and ALCOA+ checks
As a QA reviewer, I want an audit trail that cannot be silently changed, and automated ALCOA+ checks, so that I can trust the records.
- AC-3.1: Every insert into a LIMS or result table writes an audit_log row with who, what (table, key, field, old value, new value), when (UTC timestamp), and why (reason text).
- AC-3.2: Corrections are new rows that point to the record they replace. A pytest test shows that the app's write API has no update or delete path on audit_log, and that an attempted UPDATE through the API raises an error.
- AC-3.3: Each audit row stores a hash of the previous row plus its own content (a hash chain). A verify function returns OK on clean data and names the first broken row when a row is changed directly in the database (INJ-7).
- AC-3.4: ALCOA+ check results go into an `alcoa_findings` table, one row per finding with rule_id, attribute, and key. At minimum it covers: Attributable (performed_by null or not in the user list), Contemporaneous (recorded_at more than [24h] after performed_at, giving `LATE_ENTRY`), Original (raw plate CSV SHA-256 does not match the hash stored at ingestion), and Complete (an expected record is missing, for example `CUSTODY_GAP`).
- AC-3.5: Raw plate CSVs are copied to a read-only `data/raw/` area at ingestion, and their SHA-256 is stored. Processing never changes the raw files.

### US-4: Plate-reader ingestion and plate-map join
As an assay analyst, I want raw plate CSVs parsed and joined to the plate map and LIMS, so that each well knows what it holds.
- AC-4.1: The parser turns a raw 8x12 CSV into 96 rows (plate_id, well, row, col, od). A file with the wrong shape is rejected with a clear error and logged. It does not crash the run.
- AC-4.2: Each well gets a well_type (STD, BLANK, CTRL_HIGH, CTRL_LOW, SAMPLE), a nominal concentration for standards, and a sample_id plus dilution for samples.
- AC-4.3: Blank-corrected OD is the OD minus the mean of the plate blanks.
- AC-4.4: Reconciliation: a plate-map sample_id that does not match the LIMS `assayed` event for that plate (wrong plate, or the sample has no aliquot) is flagged `ID_MISMATCH` (catches INJ-2).

### US-5: 4PL standard-curve fit and back-calculation
As an assay analyst, I want a 4PL fit per plate and concentrations read back for every well, so that I get antibody levels.
- AC-5.1: Each plate's standards are fit with a 4PL model (scipy `curve_fit` or equivalent). The fit stores a, b, c, d, R², and the convergence status in a `curve_fits` table.
- AC-5.2: On a synthetic curve with known parameters and no noise, the fitted c is within 1% of the true value (pytest).
- AC-5.3: Back-calculated % recovery is stored for each standard.
- AC-5.4: Sample concentration = inverse-4PL(blank-corrected mean OD) x dilution. Signals outside the curve's working range are not extrapolated. They are labeled `<LLOQ` or `>ULOQ`.
- AC-5.5: LLOQ and ULOQ are the lowest and highest standards whose recovery is within [80-120%], in a contiguous run of passing standards.

### US-6: Plate and sample QC with accept/reject
As an assay analyst, I want rule-based QC with reason codes, so that bad plates and wells never reach the report.
- AC-6.1: These plate-level flags exist:
  - `FIT_FAIL` if the fit did not converge or R² < [0.98].
  - `STD_RECOVERY` if fewer than [75%] of standard levels recover within [80-120%].
  - `CTRL_OOR` if a high or low control falls outside its [mean ± 20%] range.
  - `BLANK_HIGH` if mean blank OD > [0.15].
- AC-6.2: A plate with any plate-level flag gets status REJECTED. All its sample results are excluded from reporting and the samples go onto the re-assay list. Otherwise the plate is ACCEPTED.
- AC-6.3: These sample-level flags exist:
  - `DUP_CV` if the duplicate CV is above [20%].
  - `BELOW_LLOQ` and `ABOVE_ULOQ`.
  - `ID_MISMATCH` (from US-4).
- AC-6.4: `ABOVE_ULOQ` samples go onto the re-assay list with a suggested higher dilution. `DUP_CV` samples go onto the re-assay list.
- AC-6.5: Each flag row stores rule_id, rule version, the measured value, and the threshold, so a reviewer can see why it fired.

### US-7: Reportable results
As a statistician, I want exactly one reportable result per sample, so that summaries are not double-counted.
- AC-7.1: `fct_reportable_result` has one row per sample_id (a dbt `unique` test), drawn only from ACCEPTED plates with no blocking flag.
- AC-7.2: When a sample was repeated, the reportable result is the latest valid run, and the choice is recorded with a reason in the audit trail.
- AC-7.3: Results below LLOQ are stored as reported "<LLOQ" plus an analysis value of 0.5 x LLOQ.
- AC-7.4: Samples with no valid result (for example, an unresolved ID_MISMATCH) appear in a `missing_results` list with a reason. They are not dropped silently.

### US-8: Immunogenicity summary (GMT, GMFR, seroresponse)
As a clinical immunology lead, I want GMT, GMFR, and seroresponse by group and visit, so that I can see whether the vaccine works.
- AC-8.1: The dbt mart `mart_immunogenicity` has one row per group x visit with n, GMT, and GMT 95% CI (t-based on log10 values).
- AC-8.2: For Day 29 and Day 57 it has GMFR vs. Day 1 with a 95% CI, using only subjects with both a baseline and a post value.
- AC-8.3: It has seroresponse n/N and % using the section 2 default definition, with a 95% Clopper-Pearson CI.
- AC-8.4: A pytest test checks GMT and GMFR against a hand-calculated 5-subject example (to 3 significant figures).
- AC-8.5: On the full run, Vaccine Day 29 seroresponse is greater than Placebo Day 29 seroresponse.

### US-9: Lab KPIs
As a lab manager, I want operational KPIs, so that I can see lab throughput and quality.
- AC-9.1: `mart_lab_kpis` contains:
  - turnaround time (received to reportable result), with median and 90th percentile, in days
  - plate failure rate (rejected / total plates) and the count of each rejection reason
  - re-assay rate
  - % of samples with complete custody
  - ALCOA+ findings per 100 records
- AC-9.2: Every KPI has a definition in `docs/METRICS.md` (owned by the Lab Informatics Analyst) that matches the SQL.
- AC-9.3: The KPI values match a pytest recompute from the base tables.

### US-10: Detection scorecard
As Michael (demo owner), I want to prove the pipeline catches the planted problems, so that the demo has a measurable result.
- AC-10.1: `detection_scorecard` joins `injected_problems.csv` to all flags and findings, and reports detected yes/no for each problem_id, with the flag that caught it.
- AC-10.2: Recall is 100% for INJ-1 to INJ-8 on the default seed. pytest fails if any planted problem is missed.
- AC-10.3: False positives (flags on records with no planted problem) are counted and reported. Target: at most [5%] of samples carry a sample-level flag not explained by an injected problem. Natural noise can legitimately cause some DUP_CV flags, so the number is reported, not hidden.

### US-11: Dashboard build spec
As an assay lab data reviewer, I want a clear dashboard design, so that I can picture the Power BI/Tableau view without installing anything.
- AC-11.1: `docs/DASHBOARD_SPEC.md` defines 3 pages:
  - Immunogenicity: GMT by group x visit (bar chart with CI error bars), a reverse cumulative distribution curve, and a seroresponse table.
  - Assay QC: plate status grid, curve fit gallery, and a Levey-Jennings style control chart.
  - Lab ops and data integrity: KPI cards, a custody funnel, and an ALCOA+ findings table.
- AC-11.2: Each visual names its source mart, fields, filters, and DAX/calc logic.
- AC-11.3: The marts are exported to CSV or Parquet in `data/marts/` for direct import into Power BI.
- AC-11.4: At least 3 static PNG charts are rendered by Python (GMT bar chart, one plate's 4PL curve with standards, plate status grid) so the README shows results without BI tools.

### US-12: One-command run and tests
As a reviewer, I want one command to rebuild everything, so that I can reproduce the demo.
- AC-12.1: One documented command on Windows runs the generator, LIMS load, ingestion, fit, QC, `dbt build`, the scorecard, and the charts, finishing in under [5] minutes on a laptop.
- AC-12.2: `pytest` and `dbt test` pass with 0 failures. The real output is pasted into HANDOFF.md.
- AC-12.3: Dependencies are pinned. There are no secrets and no network calls at runtime.

---

## 5. Injected problems (planted by the generator)

| ID | Problem | Expected detection |
|---|---|---|
| INJ-1 | One plate with a bad standard curve (a mis-pipetted standard, low R²) | FIT_FAIL or STD_RECOVERY, plate REJECTED |
| INJ-2 | Two sample IDs swapped on a plate map vs. the LIMS assay record | ID_MISMATCH |
| INJ-3 | A sample with the `received` custody step missing | CUSTODY_GAP |
| INJ-4 | A custody event recorded more than 24h after it was performed | LATE_ENTRY (ALCOA+ Contemporaneous) |
| INJ-5 | One plate with a high control out of range (curve is fine) | CTRL_OOR, plate REJECTED |
| INJ-6 | Several samples with duplicate wells far apart | DUP_CV |
| INJ-7 | One audit_log row edited directly in the database after the fact | Hash-chain verify fails at that row |
| INJ-8 | A few high-titer samples above ULOQ at the first dilution | ABOVE_ULOQ, added to re-assay list |

Optional if time allows: an aliquot with 4 freeze-thaws (FREEZE_THAW_EXCEEDED), and an event with a null performed_by (Attributable).

---

## 6. Out of scope

- Real LIMS products (LabWare, STARLIMS, and similar), instrument drivers, and robot integration. Plate CSVs are simulated.
- 21 CFR Part 11 e-signatures, user login and authentication, and role permissions beyond a static synthetic user table.
- SDTM/ADaM datasets, CRF edit checks, and EDC. These belong to the clinical-data-review project.
- Full assay method validation (precision, parallelism, stability, and similar) and statistical non-inferiority testing.
- Multiplex (Luminex/MSD) assays, cell-based neutralization curve fitting (ID50), and 5PL models. These are possible v2 items.
- Building a live Power BI/Tableau file. v1 delivers the spec, the exports, and the PNGs only.
- LLM features, cloud deployment, and Postgres as default (if D1 picks DuckDB).

---

## 7. Market evidence

Public job postings that describe the need this product addresses. Neither was re-opened; they may be closed.

- A clinical immunology posting describes blood-test assays for vaccine trials under GCLP, using robotic sample handling and a LIMS, and asks for automated analysis pipelines. https://www.linkedin.com/jobs/view/4438829272
- A vaccine R&D posting describes building AI-ready data pipelines from assay and lab notebook data. https://www.linkedin.com/jobs/view/4454595614

---

## 8. Open decisions for Michael

- D1: Database. Recommended: **DuckDB**, which has zero setup on Windows and has dbt-duckdb. The alternative is PostgreSQL, which is closer to a real LIMS backend and enforces append-only with real triggers and REVOKE, but costs setup time.
- D2: Assay type. Recommended: **ELISA IgG in AU/mL**, where 4PL fits naturally. Strictly, a concentration summary is a "GMC" not a "GMT". Reports will say "GMT/GMC". The alternative is a neutralization titer (ID50), which is more vaccine-flavored but uses a different curve method.
- D3: Seroresponse definition. Default is the 4-fold / 4 x LLOQ rule above. Confirm, or pick a fixed threshold.
- D4: Dashboard tool for the spec: Power BI (recommended) or Tableau.
- D5: Recommended: include the 2 optional injected problems only if day 1 finishes on time.
