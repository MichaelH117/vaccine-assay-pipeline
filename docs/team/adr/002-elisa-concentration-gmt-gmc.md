# ADR 002: One synthetic ELISA IgG assay, results in AU/mL, summaries labelled GMT/GMC

Status: Accepted 2026-10-29 (decision D2). Covers US-1, US-5, US-8.

## Context
The spec needs a standard curve per plate, read-back of unknowns, and geometric summaries by group and visit.
Vaccine labs run both binding assays (ELISA, reported as concentrations) and neutralization assays (reported as ID50
titers from a dilution series).

## Options
1. **ELISA IgG, concentration in AU/mL.** The 4PL standard curve and back-calculation fit naturally (US-5). The
   correct summary name is GMC.
2. **Neutralization ID50 titer.** More "vaccine" in flavour, but it needs a per-sample dilution-series curve and a
   different method. That is out of scope (SPEC section 6).

## Choice
Option 1. One assay, "Anti-Antigen X IgG ELISA (synthetic)". Samples run at 1:100. Results are
`back-calculated concentration x dilution`. Columns are named `gmt*` to match the spec and the dashboard. Every
human-readable label (METRICS.md, chart titles, DASHBOARD_SPEC.md) says "GMT/GMC (AU/mL)".

## Consequences
- The column name `gmt` is a slight misnomer. The labels say so.
- Adding ID50 later is a v2 item. It would add a new curve module and a new table, not a change to this one.
