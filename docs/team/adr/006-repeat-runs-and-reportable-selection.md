# ADR 006: Repeat runs are pre-simulated by the generator; the reportable run is chosen in Python

Status: Accepted 2026-10-29. Covers US-1, US-6, US-7, US-2 (custody order).

## Context
AC-7.2 needs "latest valid run" when a sample is repeated, with the choice recorded in the audit trail. A real lab
would schedule repeats from the re-assay list and run new plates. The pipeline runs in one pass, so there is no second
lab day.

## Options
1. Two-pass run: QC writes the re-assay list, the generator makes repeat plates, then everything is processed again.
   This is realistic but doubles the orchestration.
2. **The generator writes the repeat plates up front**, for the samples it knows it planted problems on. The pipeline
   processes all plates in one pass and does not know which ones are repeats, except through `plate_runs`.
3. No repeats. Then AC-7.2 cannot be shown.

## Choice
Option 2.
- The generator writes repeat plates (later `run_at`, `repeat_of_plate_id` set) for: all samples on INJ-1 and INJ-5
  plates, INJ-6 samples, and INJ-8 samples (at dilution x 10). INJ-2 swapped samples are not repeated, so they end up in
  `missing_results`.
- Samples that get a natural DUP_CV (noise, no repeat) also end up in `missing_results` with reason
  `REASSAY_PENDING`. That is honest and shows up in the false-positive count.
- `pipeline/reportable.py` picks, per sample, the latest `run_at` result on an ACCEPTED plate with no blocking flag.
  It writes `assay.reportable_selection` through `insert_records`, with a reason such as
  `latest valid run of 2; PLATE-003 rejected (CTRL_OOR)`. That is the audit record AC-7.2 asks for.
- Custody: each repeat adds another `assayed` event after `stored`. The CUSTODY_ORDER check compares only the first
  occurrence of each step.

## Consequences
- The generator must know the plate layout and the problem list. That logic stays in `generator/generate.py`.
- The re-assay list is still produced from flags (`core.reassay_list`). A test can check that every repeated sample was
  on that list, which links the two.

## Amendment 2026-10-29 (TL, after build)
- `assay.reportable_selection` has one row per `lims.samples` row (decision `REPORTABLE` or `NO_VALID_RESULT`,
  `n_runs` = 0 when the sample was never assayed). Ties on `run_at` break by `plate_id`.
