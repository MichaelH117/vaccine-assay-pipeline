# SPEC v2: vaccine-assay-pipeline, "real-industry" upgrade

Owner: Product Owner seat. Status: DRAFT v2.0, waiting for Michael's calls in section 10.
Date: 2026-10-30. Builds on: SPEC.md v1 (signed off in SIGNOFF.md, commit c3a93fd). Hands off to: tech-lead.
Main source: `C:\Users\stimp\projects\dev-team\research\vaccine-rnd-assay-workflow-2026-10-30.md` (written [R-n] below, where n is that file's reference number).

All data is synthetic. No real instrument file, Pfizer SOP, patient or trial record is used. Public reference numbers (Prevnar 20, the Pfizer dLIA paper) are labelled **PUBLIC REFERENCE** with a URL, and are never mixed into synthetic results.

Do not touch `site/` in this round. The Design Lead owns it and is reworking it. v2 only produces the data the site will read (US-18).

---

## 0. The question

**"Can the clinical immunology lab take files straight off its instruments, prove the assay is a trustworthy ruler, and tell leadership, per serotype, whether the 20-valent candidate is non-inferior and the program is on time?"**

Owner of the question: the clinical immunology data lead at a vaccine R&D site (persona U2). The VP (U5) is the person who has to act on the answer.

v1 answered "did the vaccine beat placebo, and did the pipeline catch planted problems" for one ELISA. v2 moves to the work Pfizer Pearl River publicly describes: a Luminex multiplex IgG assay validated against written criteria [R-11], vendor exports parsed without retyping [R-23..R-25], and FDA-style per-serotype non-inferiority and lot-consistency statistics [R-4].

---

## 1. PR/FAQ

### Press release (internal, imaginary, under one page)

**From instrument file to "19 of 20 serotypes non-inferior" with no retyping and every number traceable**

*A synthetic Pearl River style clinical immunology demo by Michael Hanson, version 2*

A pneumococcal conjugate vaccine trial is judged serotype by serotype. For Prevnar 20, FDA compared antibody titers for each of 20 serotypes and required the lower bound of the 95% confidence interval of the GMT ratio to be above 0.5. Nineteen passed. Serotype 8 came in at 0.49 [R-4] (PUBLIC REFERENCE). Every one of those numbers started as a file on a plate reader or a Luminex instrument. Every vendor writes its own file layout, and getting those files into a LIMS without mistakes is real, daily work [R-29].

`vaccine-assay-pipeline` v2 does this end to end on synthetic data. It recognizes the instrument file type by itself (SoftMax Pro-style, Gen5-style, xPONENT-style), reads it by landmarks rather than fixed row numbers, and checks it against the plate map the LIMS sent to the bench. A plate map shifted by one column is caught and named before a single wrong result is reported. A 20-serotype Luminex mode fits each serotype's curve and rejects wells with too few beads counted. A validation-style summary runs synthetic experiments through the same code and scores them against the criteria Pfizer scientists published for their 13-plex Luminex assay: 80–125% accuracy and linearity, under 20% intermediate-precision RSD [R-11]. The statistics follow the published FDA approach: below-LLOQ values set to 0.5 × LLOQ, re-run with LLOQ as a sensitivity check, a per-serotype non-inferiority test, and a 3-lot consistency test [R-4].

Then one data file feeds a one-screen executive scorecard: on track or not, five tiles with written green/amber/red rules, and the one amber explained.

"Every vendor file looks different, and the plate map is where the expensive mistakes start," said the imaginary lab data lead. "This catches the shifted map before it reaches the statistician, and shows its working."

### FAQ

**Q: Does it work with real SoftMax Pro, Gen5 or xPONENT files?** Unknown. The importers are built from public descriptions of those layouts (vendor app notes, Benchling connector guides, open-source parsers) [R-23][R-24][R-25]. They have never been run on a real instrument file. The README and every importer docstring say so. They are written to tolerate layout variation because the exact tokens are partly UNVERIFIED [research section 7].

**Q: Is the assay "validated"? Is this ICH M10 compliant?** No and no. The summary is a *validation-style* exercise on synthetic data that uses the ICH Q2(R2) parameter set [R-13] and the acceptance criteria from Pavliakova et al. 2018 [R-11]. ICH M10 does not cover immunogenicity assays [R-16], so v2 makes no M10 claim. v1's FAQ cited M10 for 4PL curve rules. v2 removes that framing for the multiplex assay (see US-16, AC-16.7).

**Q: Why not OPA, the real Prevnar 20 primary endpoint?** OPA is a different assay (colony counting, a 50%-killing titer) and would take its own build. v2 applies the FDA non-inferiority rule to synthetic **IgG GMC** from the multiplex assay and says plainly that the real adult endpoint was OPA GMT [R-4]. OPA is first on the "next" list.

**Q: Which Prevnar 20 numbers are real?** Only the ones in the reference track and the explanatory text: the 20 serotype names, the 0.5 margin, the (0.5, 2.0) lot bounds, the 0.49 serotype-8 result and the regulatory dates, each cited to the FDA memo [R-4]. All results the pipeline computes are synthetic.

**Q: Does v1 still work?** Yes. v1's ELISA study (Study A) is untouched. v2 adds a second synthetic study (Study B). v1's 245 pytest tests and 145 dbt nodes must still pass (US-19).

---

## 2. Employer grounding (Pfizer Pearl River)

| Claim | Source |
|---|---|
| Pearl River is Pfizer's vaccine R&D site; it led R&D for Prevnar 13 and Trumenba | https://www.pfizer.com/pearl-river-new-york ; VRD brochure https://cdn.pfizer.com/pfizercom/careers/P0353400_VRD_recruiting_brochure.pdf |
| The VRD brochure lists roles including assay developer, robotics programmer, systems programmer and clinical laboratory scientist, and a sample management system handling millions of trial samples | VRD brochure (above) |
| The 13-plex pneumococcal Luminex IgG assay (dLIA) was validated by Pfizer Pearl River Vaccine R&D and Biostatistics authors; acceptance criteria in section 3 come from this paper | https://pmc.ncbi.nlm.nih.gov/articles/PMC6083093/ |
| The dLIA was bridged to the WHO reference ELISA | https://pmc.ncbi.nlm.nih.gov/articles/PMC6083092/ |
| Prevnar 20 adult licensure used per-serotype OPA GMT non-inferiority (LL > 0.5), 3-lot consistency (0.5, 2.0), and 0.5 × LLOQ imputation with an LLOQ sensitivity check | FDA CBER memo STN 125731/0, https://www.fda.gov/media/150459/download |
| A published 20-serotype dLIA validation was not found. The published one covers 13 serotypes | Research section 7; PCV20 SAP https://cdn.clinicaltrials.gov/large-docs/38/NCT04530838/SAP_001.pdf |
| Which instrument software, LIMS, curve model and bead-count threshold Pearl River uses today | **UNVERIFIED.** v2 does not claim any of them. |

---

## 3. Grounding: published numbers v2 uses

| Item | Value used in v2 | Status | Source |
|---|---|---|---|
| PCV20 serotypes | 1, 3, 4, 5, 6A, 6B, 7F, 8, 9V, 10A, 11A, 12F, 14, 15B, 18C, 19A, 19F, 22F, 23F, 33F | PUBLIC REFERENCE | [R-4] |
| Non-inferiority rule | LL of 95% CI of GMT (here GMC) ratio > 0.5 | PUBLIC REFERENCE | [R-4] |
| Lot consistency | every pairwise 95% CI inside (0.5, 2.0); secondary display (0.67, 1.5) | PUBLIC REFERENCE (PCV20 and Shingrix rules) | [R-4][R-6] |
| Below-LLOQ handling | 0.5 × LLOQ primary; LLOQ as sensitivity | PUBLIC REFERENCE | [R-4] |
| Accuracy, dilutional linearity | mean relative bias 80–125% | Criterion modelled on the paper, not a Pfizer SOP | [R-11] |
| Intermediate precision | total RSD < 20% | same | [R-11] |
| Specificity | homologous inhibition ≥ 80%, heterologous ≤ 20%; 6A/6B and 19A/19F cross-reactivity expected | same | [R-11] |
| Repeatability design | ≥ 9 determinations across the range | ICH Q2(R2) | [R-13] |
| Minimum bead count per analyte per well | [50] | **Demo default, UNVERIFIED as a standard** | (no public standard found) |
| SoftMax Pro template | tab-delimited, 1 line per well, 10 columns, fixed unit list | Public vendor app note | [R-23a] |
| xPONENT CSV | ProgramMetadata block, `DataType:` sections (Median, Count, ...), Location like `1(1,A1)`, comma or semicolon | Public parser docs | [R-25a][R-25b][R-25c] |
| Gen5 export | `Results` landmark, 8×12 block; header labels partly UNVERIFIED | Public parser code + vendor note | [R-24a][R-24b][R-24c] |

---

## 4. Users and their day

Personas come from `USER_TESTING.md` (P1, P2, P8) and the roles in the research (sections 1.2 and 2.1).

| ID | Persona | Their day | Afraid of | "Wow, this gets me" |
|---|---|---|---|---|
| U1 | **Lab analyst, clinical immunology** (USER_TESTING P8; "clinical laboratory scientist" in the VRD brochure) | Runs 6–18 plates a shift [R-28a]. Exports each run, renames files, copies results into the LIMS, chases plate-map questions | A transcription or plate-map error found after unblinding | "It knew the file type, read it, and told me my map was shifted one column before I submitted" |
| U2 | **Clinical immunology data lead / lab informatics** (owner of the question) | Owns instrument-to-LIMS parsing and field mapping [R-29b], reviews QC, hands datasets to biostatistics | A silent parse error, an unexplained number in the CSR | "Every reported number traces back to a file hash, a parser version and a QC decision" |
| U3 | **Assay development / validation scientist** ("assay developer" in the VRD brochure) | Designs validation experiments, computes accuracy, linearity and precision, writes the report | Criteria applied wrongly, cross-reactive pairs miscounted as failures | "It used the published criteria, called out 6A/6B and 19A/19F correctly, and showed a real FAIL instead of hiding it" |
| U4 | **Biostatistician, early clinical development** (co-author role on the dLIA paper [R-11]) | Programs GMC/GMR, NI tests and lot consistency, mostly in SAS (UNVERIFIED for Pfizer) | Imputation choices changing a conclusion without anyone noticing | "The sensitivity analysis is there and flags exactly which serotypes it would change" |
| U5 | **VP / Director, Vaccine R&D** (USER_TESTING P1), plus **board member, 68, reading glasses** (P2) | 30 seconds per program: "are we on track, what do you need from me?" | A program that stays green while the science stalls [R-32c] | One verdict, five tiles, the one amber explained, a decision asked |

Workflow v2 (Study B, one plate):
1. LIMS exports a SoftMax-style plate-map template (US-14).
2. The bench runs the plate. The instrument writes an xPONENT-style CSV (multiplex) or a SoftMax/Gen5-style text file (ELISA).
3. The pipeline sniffs the format, parses it, hashes the raw file and records vendor/software/build (US-13).
4. The template is matched to the LIMS assay records. Shifts are caught (US-14).
5. Per-serotype curve fit, bead-count QC and plate QC (US-15).
6. Reportable results feed the GMC, NI and lot-consistency marts (US-17).
7. Validation-study plates run through the same code to give the validation summary (US-16).
8. The scorecard feed and stage-gate data are written for the site (US-18).

---

## 5. Ontology (objects, links, actions)

| Object | Key properties | Links |
|---|---|---|
| InstrumentFile | file_id, detected_format, vendor_label, software_version, build, sha256, parser_version, import_status | → Plate (1..n) |
| PlateMapTemplate | template_id, plate_id, version, sha256, source (LIMS export / bench edit) | → Plate; → Well |
| Plate | plate_id, study, assay_mode (ELISA / MULTIPLEX20), status | → Well; → InstrumentFile |
| Well | well, group_type, sample_id, dilution | → AnalyteReading |
| AnalyteReading | analyte (serotype), median_mfi or od, bead_count | → Well |
| Lot | lot_id (synthetic A/B/C) | → Subject |
| ValidationExperiment / ValidationResult | parameter, serotype, value, criterion, verdict | → Plate |
| NIComparison | serotype, gmr, ci_low, ci_high, met, imputation_rule | |
| StageGate | gate, planned_date, actual_date, rag, track (SYNTHETIC / PUBLIC REFERENCE), source_url | |
| ScorecardTile | tile_id, value, denominator, threshold_text, rag, confidence_note | |

| Action | Who may | Inputs | Validation | Side effects | Undo |
|---|---|---|---|---|---|
| Import instrument file | pipeline (as a named service user) | file path | format detected; required landmarks present; well count and analyte list match the plate | raw copy made read-only, hash stored, audit row | none. A bad import is rejected and logged, never half-loaded |
| Import plate-map template | analyst role (synthetic user table) | template file | 10 columns; known group types; units in the allowed list; every well once | audit row; shift check runs | a corrected template is a new version with a reason; old version kept |
| Correct plate map | analyst, then a second-person review (synthetic user) | new template + reason | reason text required; reviewer ≠ author | audit row with both users; plate re-evaluated | supersede again; nothing deleted |
| Accept / reject plate | rules engine | QC flags | rule version recorded | re-assay list | re-run creates a new plate run |
| Publish scorecard feed | pipeline | marts + `config/scorecard.yaml` | every tile has a threshold and a source | JSON written with run id and rules version | regenerated each run |

---

## 6. User stories and acceptance criteria

All new thresholds live in config with a version string (`config/qc_rules.yaml` → `QC-RULES-2.0`, plus `config/scorecard.yaml`). Defaults are in brackets. Priority: **M** = must, **S** = should (cut line in section 9).

### Synthetic Study B (shared by US-15 to US-18)
A synthetic immunobridging study: Candidate 20-valent vs Comparator, [150] subjects per arm, visits Day 1 and Day 29 (1 month post), multiplex IgG in µg/mL for 20 serotypes. Candidate subjects are spread evenly across 3 synthetic lots (A, B, C). Fixed seed. Exact size is the tech-lead's call, as long as AC-19.3 (runtime) holds.

### US-13 (M): Vendor-format importers with auto-detection
As a lab analyst (U1), I want the pipeline to recognize and read instrument exports as they come off the instrument, so that nobody retypes or reshapes results.
- AC-13.1: The generator writes each Study A ELISA plate in 3 renderings: v1 generic CSV, SoftMax Pro-style plate block (`##BLOCKS=`, `~End`), and Gen5-style text (`Software Version` header, `Results` block with `Read 1:450` labels). It writes each Study B plate as an xPONENT-style CSV with a ProgramMetadata block and at least the `Median` and `Count` DataType sections. Every synthetic file starts or ends with a comment or metadata line marking it SYNTHETIC, where the format allows.
- AC-13.2: A detector reads only the first [20] lines and returns one of `softmax_plate`, `gen5_text`, `xponent_csv`, `generic_csv`, or `unknown`. A pytest test covers every rendering and at least 3 non-plate files (empty file, random CSV, a SoftMax template file), which must not be detected as plate data.
- AC-13.3: Parsers find landmarks, not fixed row numbers. One test per parser feeds variants that must all parse to the same values: extra blank lines, header lines in a different order, CRLF vs LF, UTF-8 BOM, trailing tabs. For xPONENT: comma and semicolon delimiters, and DataType sections in a different order.
- AC-13.4: Round trip: for every Study A plate, the SoftMax-style, Gen5-style and generic renderings parse to the same 96 OD values (exact equality after rounding to the file's printed precision).
- AC-13.5: `lims.raw_files` gets new columns: detected_format, vendor_label, software_version, build (xPONENT), parser_version. The raw-file SHA-256 and read-only copy from v1 AC-3.5 apply to every format.
- AC-13.6: An `unknown` or broken file (INJ-14) is rejected with `IMPORT_FAIL` and a reason naming the missing landmark (for example "no `DataType:,Median` section"). The run continues. Nothing from that file reaches any table except the import log.
- AC-13.7: The xPONENT `CRC32` line is stored but not verified, and the import log says "checksum not verified: vendor algorithm scope UNVERIFIED".
- AC-13.8: Each importer module docstring and the README importer section contain: "Modelled on public format descriptions; not tested against real instrument output."

### US-14 (S): Plate-map template import and the shifted-column check
As a lab data lead (U2), I want the plate map to travel as a SoftMax-style template file and be checked against the LIMS, so that a shifted map is caught before results are reported.
- AC-14.1: The LIMS writes one template per plate: tab-delimited UTF-8, one line per well, the 10 columns in the vendor app-note order [R-23a]. Group types are Standards, Unknowns or Custom (controls and blanks are Custom). Descriptor1 holds dilution or concentration, with units only from the app note's list.
- AC-14.2: Template import rejects, with a reason: wrong column count, a well listed twice, a well outside A1–H12, an unknown group type, or a unit not in the list. A blank group name makes the rest of that line ignored, as the app note says.
- AC-14.3: INJ-12: for one Study B plate, the generator writes a template where sample names in one row (or the whole plate, tech-lead's choice) are shifted one well to the right. The LIMS assay record is correct.
- AC-14.4: A rule `PLATEMAP_SHIFT` fires when at least [3] sample wells mismatch the LIMS and shifting the template by one column (±1) explains at least [90%] of the mismatches. The flag stores the direction and offset ("shifted +1 column, row C") and the count explained. Plain `ID_MISMATCH` (v1) still fires for mismatches the shift does not explain.
- AC-14.5: A plate with `PLATEMAP_SHIFT` is held (status `HOLD_PLATEMAP`), and none of its results are reportable. When a corrected template version is imported with a reason and a different reviewer, the plate is re-evaluated and can be accepted. Both template versions and both users are in the audit trail.
- AC-14.6: The default seed has 0 `PLATEMAP_SHIFT` flags on plates without INJ-12.

### US-15 (M): 20-serotype multiplex (Luminex-style) mode with bead-count QC
As a lab analyst (U1), I want each well read for all 20 serotypes, with wells that counted too few beads set aside, so that one plate gives up to 20 trustworthy results per sample.
- AC-15.1: The xPONENT parser returns one row per plate × well × analyte with median_mfi and bead_count, joining the `Median` and `Count` sections on Location. Location strings like `1(1,A1)` are decoded to well A1. A test covers all 20 PCV20 serotype names, including "6A", "6B", "19A", "19F" (which must not be mixed up).
- AC-15.2: Each plate has a reference-serum standard curve per serotype (the dLIA used 11 points at 2.5-fold [R-11]). A curve is fitted per plate × serotype with the model chosen in D7, and fit status, parameters and working range are stored per serotype.
- AC-15.3: `LOW_BEAD_COUNT` fires per well × serotype when bead_count < [50]. That serotype result for that well is excluded. Other serotypes in the same well are kept. The flag stores the count and threshold.
- AC-15.4: INJ-13: the generator plants low bead counts on [1] well for [3] serotypes and on [1] whole well (all 20 serotypes, mimicking a clog). All are caught. The whole-well case is reported as one well-level event plus 20 analyte flags.
- AC-15.5: Plate-level QC from v1 (fit, standard recovery, controls, blank) is applied per serotype. A plate is rejected for one serotype only, not for all 20, unless more than [3] serotypes fail. The rule and reason are stored. (Partial-plate acceptance per analyte matches how multiplex results are reported per serotype. This is a demo rule, UNVERIFIED as industry practice.)
- AC-15.6: `fct_reportable_result` gains an `analyte` column. Uniqueness becomes sample_id × analyte (dbt test). Study A rows get analyte `IgG_ELISA`.
- AC-15.7: The detection scorecard includes INJ-12, INJ-13 and INJ-14, and recall stays 100% on the default seed and on a [6]-seed sweep.

### US-16 (S): Validation-style summary using ICH Q2(R2) parameters and published criteria
As an assay validation scientist (U3), I want synthetic validation experiments run through the real pipeline and scored against written criteria, so that the "is the ruler trustworthy?" question has an evidence table.
- AC-16.1: The generator writes a separate validation run set (not mixed with Study B): accuracy samples at 3 dilution levels, a dilutional linearity series (at least [6] dilutions), repeatability (at least 9 determinations: 3 levels × 3 replicates [R-13]), an intermediate-precision design varying analyst × day × bead lot, and an inhibition (specificity) experiment. All of it goes through US-13 and US-15 code, not a side path.
- AC-16.2: The summary computes per serotype: accuracy (mean relative bias), dilutional linearity (relative bias per dilution), repeatability RSD, intermediate-precision total RSD (variance components, method stated in the report), LLOQ, range as fold, and specificity (homologous and heterologous % inhibition).
- AC-16.3: Each parameter has a PASS/FAIL verdict against config criteria (defaults from section 3). The criteria table cites Pavliakova et al. 2018 [R-11] and ICH Q2(R2) [R-13] and is headed "criteria modelled on a published paper; not a Pfizer SOP".
- AC-16.4: Heterologous inhibition above 20% for the pairs 6A/6B and 19A/19F is labelled `EXPECTED_CROSS_REACTIVITY` with the citation, not FAIL. Only pairs listed in config get this label. An unlisted pair above 20% is FAIL.
- AC-16.5: PLANT-VAL-1: one serotype is generated with intermediate precision about [22%] RSD and must come out FAIL. The summary does not average it away, and the scorecard tile (US-18) shows "N of M parameters met".
- AC-16.6: Output: `docs/validation/ASSAY_VALIDATION_SUMMARY.md` (generated, not hand-written) and `data/marts/mart_assay_validation.csv`. Every number in the .md comes from the mart (pytest compares them).
- AC-16.7: The words "validated", "compliant" and "M10" do not appear in the generated summary or the v2 README section except inside the sentences "not a validated method", "no compliance claim" and "ICH M10 does not cover immunogenicity assays" (a grep test enforces this).

### US-17 (M): FDA-style statistics: imputation sensitivity, non-inferiority, lot consistency
As a biostatistician (U4), I want per-serotype GMC ratios with the published decision rules and a sensitivity check, so that I can see which conclusions are robust.
- AC-17.1: `mart_ni_serotype` has one row per serotype × imputation rule (`HALF_LLOQ` primary, `LLOQ` sensitivity) with n per arm, GMC per arm, GMR (Candidate / Comparator), and the 95% CI from a t-based interval on log-transformed values. `met` = CI low > [0.5].
- AC-17.2: A pytest test checks GMR and CI against a hand-calculated example of [6] subjects per arm to 3 significant figures, for both imputation rules.
- AC-17.3: A column `conclusion_changes_under_sensitivity` is true for any serotype whose `met` differs between the two rules. The report lists those serotypes by name, or says "none".
- AC-17.4: PLANT-NI-1: the generator sets one serotype's true ratio so its CI lower bound falls in [0.45, 0.50) on the default seed. It must show `met = false`. The other 19 must show `met = true`. Text next to it says this mirrors the pattern of the real PCV20 serotype 8 result (LL 0.49) [R-4], and that the number here is synthetic. (D8 picks which serotype carries it.)
- AC-17.5: `mart_lot_consistency` has one row per serotype × lot pair (A/B, A/C, B/C) with the GMC ratio and 95% CI, and two verdict columns: `within_0_5_2_0` (primary, PCV20 rule [R-4]) and `within_0_67_1_5` (shown for comparison, Shingrix rule [R-6]). The overall lot-consistency verdict uses only the primary rule.
- AC-17.6: On the default seed, all 60 pairs meet the primary rule. Results under the secondary rule are reported as they come out, without tuning.
- AC-17.7: Planted outcomes (PLANT-NI-1, PLANT-VAL-1) are listed in `planted_outcomes.csv`, separate from `injected_problems.csv`, so they never count toward detection recall.

### US-18 (S): Stage-gate program data and the exec scorecard feed
As a VP (U5), I want one verdict, five tiles and the gate timeline as data the site can render, so that I know in 30 seconds whether we are on track and what I am being asked to decide.
- AC-18.1: `data/marts/program_stage_gates.csv` has two tracks. **SYNTHETIC**: Discovery → Preclinical → Ph I → Ph II → End-of-Phase 2 → Ph III → BLA → PDUFA for an invented program, with plan date, actual or forecast date, RAG, and assay milestones pinned to gates (assay qualified before Ph II, validation summary before Ph III samples, validation report in BLA). **PUBLIC REFERENCE**: the PCV20 dates from the FDA memo (pre-IND Feb 7 2013, EoP2 Sep 18 2018, BLA received Oct 8 2020, review completed Jun 8 2021) [R-4]. Every reference row has a non-empty `source_url`. A test fails if any reference row lacks one.
- AC-18.2: `data/marts/exec_scorecard.json` has exactly 5 tiles: (1) Study B samples reported vs plan, (2) first-pass plate acceptance, (3) median turnaround vs target, (4) validation parameters met (from US-16), (5) serotypes meeting non-inferiority (from US-17). Each tile has value, denominator, unit, threshold text, RAG, a one-sentence plain-English note, a confidence note (high/medium/low with a reason) [R-32c], and the source mart and column.
- AC-18.3: RAG thresholds live in `config/scorecard.yaml` in words a VP can read ("Green if at least 95% of planned samples are reported"). A test recomputes each RAG from the marts and the config.
- AC-18.4: The feed has a `verdict` sentence and a `decision_asked` sentence built from the tiles. Rule: any RED tile gives "At risk", any AMBER gives "On track with N item(s) to watch" (wording per D9), otherwise "On track". On the default seed the NI tile is AMBER (19 of 20) and the verdict names the serotype.
- AC-18.5: Every string in the feed passes a plain-language check: no idioms from USER_TESTING section P7, each acronym expanded on first use within the tile (for example "geometric mean ratio (GMR)"). A test checks the acronym rule against a small list.
- AC-18.6: The feed carries `synthetic: true`, the run id, rules version and build commit. It contains no hex hashes or event IDs in tile text (USER_TESTING P1 minor finding).
- AC-18.7: No file under `site/` is changed by v2 engineering. The Design Lead decides how to show the feed.

### US-19 (M): Regression, one command, honesty
As Michael, I want v1 to keep working and v2 to stay honest, so that the upgrade does not cost the signed-off demo.
- AC-19.1: All v1 tests still pass. Study A seed-42 headline numbers in `results.json` (13 of 13 caught, 358/360 reportable, GMT 4,332.9) are unchanged.
- AC-19.2: One command still builds both studies, the validation set, all marts, the scorecard feed and the validation summary.
- AC-19.3: Full build (without tests) runs in under [5] minutes on the reference laptop, measured and pasted into HANDOFF.
- AC-19.4: README gets a v2 section that lists, in plain words: formats are modelled not tested, the summary is validation-style not a validation, no M10 claim, IgG used where the real PCV20 adult endpoint was OPA, Prevnar 20 numbers are public reference data with links.
- AC-19.5: No new runtime network calls. New dependencies (if any) are pinned.

---

## 7. Injected problems and planted outcomes (new in v2)

| ID | Kind | What is planted | Expected detection / outcome |
|---|---|---|---|
| INJ-12 | problem | Plate-map template shifted one column on one Study B plate | `PLATEMAP_SHIFT`, plate `HOLD_PLATEMAP` |
| INJ-13 | problem | Low bead counts: 3 serotypes in one well, plus one whole well | `LOW_BEAD_COUNT` per analyte; well-level event |
| INJ-14 | problem | One truncated xPONENT file (no `Median` section) and one unknown-format file | `IMPORT_FAIL` with the missing landmark named; run continues |
| PLANT-NI-1 | outcome | One serotype true GMR set so CI low lands in [0.45, 0.50) | NI `met = false`; scorecard AMBER |
| PLANT-VAL-1 | outcome | One serotype intermediate precision about 22% RSD | Validation FAIL row |

---

## 8. Four risks

| Risk | Owner | What could go wrong | How we test it |
|---|---|---|---|
| Value | PO | A Pearl River reviewer sees "toy formats" or the wrong endpoint and stops reading | Sign-off checks that each story names its public source; ask one lab-scientist reader (USER_TESTING P8 role) to review the v2 README section; FAQ is explicit about OPA vs IgG |
| Usability | design-lead | The scorecard is a wall of numbers; the amber reads as failure | AC-18.2 to 18.6; UX researcher reruns the 5-second test on the site using the feed |
| Feasibility | tech-lead | 20 serotypes × curves × plates is slow; landmark parsing is fiddly; variance components need a new dependency | AC-19.3 runtime budget; cut line in section 9; tech-lead may choose a simple nested-ANOVA estimate over a mixed-model package |
| Business viability (honesty, GxP, legal) | PO | Overclaiming instrument compatibility, validation status or M10; vendor trademarks used as if endorsed; implied use of real data | AC-13.8, AC-16.7 grep test, AC-19.4; importer names use "-style"; no vendor logos; synthetic marker in every generated file |

---

## 9. Scope, cut line and out of scope

Estimated build: about 2 days for the M stories plus US-16 or US-14. If day 1 runs late, cut in this order (last cut first): US-18 stage-gate track (keep the scorecard JSON), then Gen5-style renderer (keep SoftMax + xPONENT), then US-14, then US-16 specificity (keep accuracy, linearity, precision).

**Out of scope for v2 (cut ideas, kept for "next"):**
1. OPA titer module and complement-lot QC (research #4). Next in line.
2. OOS / invalid-run investigation workflow with Phase I/II records and e-signature style approvals (research #9).
3. Lab capacity and turnaround simulation, liquid-handler log importer (research #10).
4. Tecan Magellan .xlsx, MSD Discovery Workbench and BMG MARS importers.
5. ELISA-vs-Luminex bridging page with Deming regression [R-12].
6. Any change under `site/` (Design Lead owns it).
7. Real 21 CFR Part 11 controls, user login, real LIMS integration, SDTM/ADaM, SAS output.
8. 5PL and log-log-linear models beyond what D7 picks; parallelism equivalence testing (USP <1032>) [R-17].
9. Verifying the xPONENT CRC32.
10. Any claim of real instrument compatibility, assay validation, or ICH M10 coverage.

---

## 10. Job postings this project proves skills for

| Posting | Skills v2 adds | Source |
|---|---|---|
| Pfizer, Scientist, Vaccine Immunology | Multiplex serology data, validation criteria, per-serotype statistics | https://www.pfizer.com/about/careers/job/4959245 (from research [R-20]; I did not reopen it, posting may be closed) |
| Pfizer, Scientist, Ligand Binding Assay Development | Curve fitting, accuracy/precision/linearity, LLOQ and range | https://www.pfizer.com/about/careers/job/4963445 (same caveat) |
| Pfizer Pearl River clinical immunology (GCLP, LIMS, automated analysis pipelines) | Instrument-to-LIMS parsing, plate-map control | https://www.linkedin.com/jobs/view/4438829272 (from v1 SPEC; not reopened) |
| Pfizer vaccine R&D, AI-ready data pipelines from assay data | Tidy per-analyte data model, file provenance | https://www.linkedin.com/jobs/view/4454595614 (from v1 SPEC; not reopened) |
| Merck, Veeva, Aquestive data roles | Same | UNVERIFIED (no posting URL) |

---

## 11. Open decisions for Michael

- **D6, Study design.** Recommended: add Study B (20-plex immunobridging) beside v1's Study A, so the signed-off v1 demo stays intact. Alternative: convert Study A to multiplex (less code, but it breaks v1 sign-off numbers).
- **D7, Multiplex curve model.** Recommended: reuse the v1 4PL per serotype (already tested, fastest). Alternative: log/log-linear, which is what the Pfizer dLIA paper used [R-11]. More faithful, about half a day more. Either way, the README states which model and that the paper used log/log-linear.
- **D8, The near-miss serotype.** Recommended: plant it on serotype 8 to mirror the real PCV20 result, clearly labelled as synthetic. Alternative: a different serotype, to avoid looking like we copied real data.
- **D9, Scorecard verdict wording when one serotype misses.** Recommended: "On track, 1 item to watch: serotype 8 narrowly missed non-inferiority (lower bound 0.4x, needed above 0.5)", with the real computed value filled in. Alternative: "At risk", which is more conservative.
- **D10, Cut order if time is short.** Confirm the order in section 9 (importers and stats first, site feed and Gen5 last).
