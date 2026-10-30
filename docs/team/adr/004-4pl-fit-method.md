# ADR 004: 4PL fit with scipy.optimize.curve_fit

Status: Accepted 2026-10-29. Covers US-5, US-6.

## Context
Each plate needs a 4PL standard curve, back-calculated recovery, a working range, and sample concentrations
(AC-5.1 to AC-5.5). The Engineering Manager asked for `scipy.optimize.curve_fit` and few dependencies.

## Options
1. **scipy `curve_fit`, unweighted least squares.** One small, well-known dependency.
2. Weighted fit (1/y^2) or a 5PL model. Better at the curve ends, but more to explain and test. 5PL is out of scope.
3. A dedicated package (for example `drc`-style libraries). Extra dependency, less transparent.

## Choice
Option 1, with these fixed rules:
- Model `y = d + (a - d) / (1 + (x / c) ** b)`. x = nominal concentration (AU/mL), y = blank-corrected OD.
- Fit all 16 standard wells (both replicates), not the duplicate means.
- Starting values: a = min(y), d = max(y), c = median nominal concentration, b = 1. Bounds: b in (0.1, 10),
  c in (min x / 10, max x * 10). `maxfev` from config.
- `RuntimeError` or `OptimizeWarning` from scipy, or any non-finite parameter, means `converged = False`. That gives
  FIT_FAIL. Never crash the run.
- R² = 1 - SS_res / SS_tot on the fitted points.
- Inverse: `x = c * ((a - d) / (y - d) - 1) ** (1 / b)`. Recovery = inverse(mean duplicate OD) / nominal x 100.
- Working range (AC-5.5): the longest contiguous run of standard levels with recovery in 80-120%. LLOQ/ULOQ are its
  lowest/highest nominal concentrations. A sample OD outside [f(LLOQ), f(ULOQ)] is labelled `<LLOQ`/`>ULOQ` and is
  not extrapolated.
- DUP_CV is computed on the blank-corrected OD of the two duplicate wells. It is always computable, including for
  samples outside the range.

## Consequences
- Unweighted fits can be less accurate at the low end. That is acceptable for a demo, and the recovery rules catch it.
- One extra dependency (scipy), which also supplies the t and beta quantiles for US-8.
- DUP_CV on OD is not the same as CV on concentration. METRICS.md says which one is used.
