# ADR 003: Seroresponse rule, and which LLOQ to use for reporting

Status: Accepted 2026-10-29 (decision D3). Covers US-5, US-7, US-8.

## Context
The spec's default seroresponse rule uses "LLOQ", and below-LLOQ results are imputed as 0.5 x LLOQ. But each plate
has its own working range (AC-5.5). If the bottom standard fails on one plate, that plate's LLOQ is higher. Using
per-plate LLOQs in subject-level statistics makes the same subject's baseline and Day 29 values use different cut-offs.

## Options
1. Per-plate LLOQ everywhere.
2. **A fixed assay-level LLOQ for reporting and statistics, with the per-plate range only deciding `<LLOQ`/`>ULOQ`
   labels.** This is how protocols usually state it: one assay LLOQ.
3. A fixed threshold (for example a seroprotection cut-off) instead of a fold rule.

## Choice
Option 2, with the spec's default rule.
- `assay_lloq_au_ml` = lowest standard x default dilution (0.4572 x 100 = 45.72 AU/mL), from the config.
- A sample is reported `<LLOQ` when its signal is below the plate's working range, or its concentration is below
  `assay_lloq_au_ml`. Its analysis value is `0.5 x assay_lloq_au_ml`.
- Seroresponse (per subject, post visit vs D1): if baseline is `<LLOQ`, responder when post >= 4 x LLOQ. If baseline
  is >= LLOQ, responder when post / baseline >= 4. Fold and LLOQ come from config.
- N = subjects with a reportable result at both D1 and the post visit. The CI is Clopper-Pearson.

## Consequences
- Simple and the same for every subject. METRICS.md must state the rule in words, and `test_stats.py` must cover the
  boundaries (exactly 4x, baseline exactly at LLOQ).
- If Michael picks a fixed threshold later, only `is_seroresponder` and two config keys change.

## Amendment 2026-10-29 (TL, after build)
- `BELOW_LLOQ` and `ABOVE_ULOQ` flags are raised on ACCEPTED plates only. On a REJECTED plate the curve is not
  trusted; `sample_results.range_flag` is still stored when a curve exists, and is null when the plate has no
  converged curve or no working range. Rejected-plate samples go to the re-assay list at their current dilution.
