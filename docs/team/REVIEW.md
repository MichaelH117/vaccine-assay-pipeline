# Code review: Phase 0-2 build

Reviewer: Tech Lead seat, 2026-10-29. Scope: correctness of the 4PL fit and back-calculation, QC rules vs
`config/qc_rules.yaml`, reportable selection, GMT/GMFR/seroresponse, the audit hash chain, and the detection scorecard.
I read the code and queried the seed-42 build (`data/warehouse/vaccine_assay.duckdb`). I changed no product code.

Severity: **High** = a control does not do what the docs claim. **Medium** = wrong or misleading result under plausible
conditions, or a test that can pass while the feature is broken. **Low** = edge case, cleanup, or missing test.

## Verified correct (no action)
- `inverse_four_pl` is the exact algebraic inverse of `four_pl` and returns NaN outside the asymptotes. Samples outside
  [f(LLOQ), f(ULOQ)] are labelled and never extrapolated (AC-5.4). Clean plates fit with R2 0.9995 or better.
- A failed fit (exception, non-finite params, fewer than 5 points) returns `converged=False` with a message. Downstream,
  controls and samples get null concentrations, and the plate is REJECTED. Nothing raises.
- The QC thresholds and comparison directions in `pipeline/qc.py` match the config: FIT_FAIL `< 0.98`; STD_RECOVERY
  `< 0.75` of levels within 80-120% inclusive; CTRL_OOR outside target ±20% inclusive; BLANK_HIGH `> 0.15` on raw
  blank OD; DUP_CV `> 20%`. Boundary tests exist for each one.
- `reportable.choose` picks the latest valid run, sorted by `run_at` then `plate_id`. A valid run is on an ACCEPTED
  plate, has no blocking flag, and is IN_RANGE or <LLOQ. A later invalid run never replaces an earlier valid one. The
  reason is audited. Seed 42 result: 358 REPORTABLE, and the 2 NO_VALID_RESULT samples are the INJ-2 swap.
- `stats.py`: the GMT and GMFR CIs are t-based on log10, and GMFR is paired per subject. Clopper-Pearson uses the
  correct beta quantiles, including the 0/n and n/n edges. Seroresponse follows ADR 003. In the mart, the seroresponse
  denominator is the paired-subject count, and D1 rows have null GMFR and sero columns.
- `verify_chain` covers in-place edits, deletes, reorders, and a re-hashed forged row that breaks at the next row.

## Findings, most important first

### F1. High: tamper detection only covers the audit log, not the records. Owner: GXP
`pipeline/audit.py:381-408` (`verify_chain`), `generator/tamper.py:38`, `tests/test_audit.py:286-301`.
- The hash chain protects `audit.audit_log` rows. Nothing compares a base-table row (`lims.*`, `assay.*`) with the
  `new_value` JSON in its INSERT audit row.
- INJ-7 edits the audit row, so the chain catches it. The more realistic fraud is `UPDATE lims.custody_events SET
  performed_at = ...`, and that goes undetected today: the chain stays OK and LATE_ENTRY simply reads the forged
  value.
- GXP-06 compares row counts only, not content.
- **Fix:** add a reconciliation step to `integrity.py`. For each audited table, compare `canonical_json(row)` with the
  latest INSERT plus CORRECTION payloads by `record_key`, and write mismatches to a new `RECORD_MISMATCH` finding
  (ALCOA Original). Then add a second tamper variant that edits a base row, and test both.
- Until then, ADR 001 (amended) and the validation pack must state the gap.

### F2. Medium: the false-positive metric ignores plate-level false rejects. Owner: LIA (metric), QA (test)
`dbt/models/marts/scorecard_false_positives.sql:15-23`, `tests/test_qc.py:85-89`.
- The FP rate counts only sample-level flags. A plate wrongly REJECTED removes 37 samples from reporting and adds 0 to
  `fp_pct`.
- `test_inj1_and_inj5_plates_rejected` asserts that the planted plates are rejected. It does not assert that the other
  plates are accepted in the dirty build. `test_clean_build_rejects_no_plate` covers the clean build only.
- **Fix:** add `plates_total` and `plates_rejected_unexplained` to `scorecard_false_positives`. Assert that the
  REJECTED set in `built` equals exactly the INJ-1 and INJ-5 plates.

### F3. Medium: cascading plate flags can satisfy the scorecard for the wrong reason. Owner: LIA (scorecard), DE (qc)
`pipeline/qc.py:44-50`, `dbt/models/marts/detection_scorecard.sql:32-38`.
- CTRL_OOR is raised whenever a control's back-calculated concentration is out of range or not computable. That
  includes any plate whose curve is broken.
- On seed 42, PLATE-007 (INJ-1, bad standards) also carries `CTRL_OOR:HIGH` and `CTRL_OOR:LOW`, both computed from
  the broken curve.
- So INJ-5 ("control off, curve fine") would score as detected even if the control rule were deleted and the plate
  merely failed its fit.
- **Fix:** match INJ-5 only when the plate has CTRL_OOR and no FIT_FAIL or STD_RECOVERY, which is what the INJ-5
  description promises. Or skip CTRL_OOR when FIT_FAIL is present and mark the cascade in the message.
- Also add a unit test that INJ-5 is caught on a plate whose fit passes.

### F4. Medium: a fit that stops at a parameter bound counts as "converged". Owner: DE
`pipeline/curve.py:91-92, 114`.
- PLATE-007 fit `c = 10000.00`, which is exactly the upper bound (`x.max() * 10`), and `b = 0.50`. It is stored as
  `converged=True, fit_message='converged'`.
- Here R2 0.91 still fails the plate, but a bound-pinned fit with R2 ≥ 0.98 would pass and back-calculate from a
  meaningless curve.
- **Fix:** if any parameter is within a small tolerance of its bound, set `converged=False` (or keep it True but make
  FIT_FAIL fire) with the message `parameter c at bound`. Add a unit test.

### F5. Medium: deleting the newest audit rows (tail truncation) is not detected. Owner: GXP
`pipeline/audit.py:381-408`.
- `verify_chain` checks the chain from the genesis row forward. Deleting the last N rows leaves a valid shorter chain.
  `chain_verify` lives in the same file, so it is no anchor.
- **Fix (cheap):** at the end of `build`, write the head `audit_seq` and `row_hash` to `docs/results.json` as an
  external anchor, and have `verify_chain` optionally compare against an expected head.
- Also run the GXP-06 count reconciliation inside the pipeline, not only in pytest. Document this as a residual risk
  either way.

### F6. Low: a scorecard test can never fail. Owner: LIA
`tests/test_scorecard.py:32-36`.
- `caught_by` is built only from flags joined to `expected_flags` (`detection_scorecard.sql:36-37`), so "caught by an
  expected flag" is always true.
- **Replace it with a test that can fail.** For example:
  - assert each planted key's `caught_by` against a hard-coded expected value;
  - or build with QC rules disabled and assert recall drops.

### F7. Low: "explained" in the FP metric is very loose. Owner: LIA
`dbt/models/marts/scorecard_false_positives.sql:29-33`.
- Any flag on a sample linked to any injected key counts as explained. For example, a natural DUP_CV on an INJ-2 or
  INJ-3 sample is excused.
- Sample-level truth also matches a flag on any plate, not the planted one.
- Tighten this so a flag is explained only when its code is in `expected_flags` for that sample's INJ type. Accept the
  cross-plate match, but say so in METRICS.md.

### F8. Low: a NaN mean OD is labelled IN_RANGE with a null concentration. Owner: DE
`pipeline/curve.py:129-131`.
- Neither comparison is true for NaN, so the label falls through to `IN_RANGE` with `conc_au_ml` null. Such a run
  could be picked as reportable.
- `mart_immunogenicity.py:39` would then silently drop it, and `reported_value` would be null.
- It cannot happen today, because `parse_plate_csv` rejects a missing OD. Guard it anyway: NaN gives a null
  range_flag.

### F9. Low: a sample that is >ULOQ on a rejected plate is re-assayed at the same dilution. Owner: DE
`dbt/models/core/reassay_list.sql:21-22`.
- This is a consequence of approved change C5: there is no ABOVE_ULOQ flag on rejected plates.
- Acceptable for v1. Optionally, suggest dilution x10 when `range_flag = '>ULOQ'` on a rejected plate that still has
  a curve.

### F10. Low: DUP_CV is computed on blank-corrected OD near zero. Owner: DE
`pipeline/curve.py:134-136`.
- For near-blank samples the mean is near 0, so the CV blows up. Seed 42 shows no natural DUP_CV, but a lower placebo
  titer would produce false positives.
- Consider applying DUP_CV only when `mean_od >= lloq_od`, or document the behaviour in METRICS.md.

### F11. Low: missing tests for the immunogenicity mart. Owner: LIA (LIA-07)
- There is no test of `mart_immunogenicity.build_rows`: paired subset only, D1 nulls, `sero_total` = paired n, a
  subject missing D1 excluded from GMFR.
- There is also no recompute of mart GMT from `fct_reportable_result` on `built`. `test_stats.py` covers only the pure
  functions.

### F12. Low: `assay_lloq_au_ml` is hard-coded, not derived. Owner: DE
`config/qc_rules.yaml:11`.
- 45.72 duplicates `std_levels_au_ml[-1] x default_dilution`. Add a `load_rules` check that they agree.

## Contract changes (decisions; DESIGN.md section 10)
C1 DB rename: approved. C2 `sero_total`: approved. C3 `checked_at`: approved. C4 `flag_id` format: approved.
C5 range flags on accepted plates only: approved (see F9). C6 `SYS-PIPELINE` actor: approved as a system account.
C7 added columns: approved.
