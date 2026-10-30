# ADR 005: What runs in Python and what runs in dbt, and one config file for both

Status: Accepted 2026-10-29. Covers US-2 to US-9, and the file ownership in DESIGN.md section 2.

## Context
Three seats build in parallel. The audit trail must record every insert into a base table (AC-3.1), and dbt cannot
call the audit API. Curve fitting needs scipy. Confidence intervals need t and beta quantiles, which DuckDB SQL lacks.
Thresholds must live in one versioned config (SPEC section 4).

## Options
1. Everything in Python (pandas). Simple, but no dbt lineage or dbt tests, which the target roles ask for.
2. Everything possible in dbt SQL. Not possible for 4PL, audited writes, or quantiles.
3. **Split by kind of work**, with a fixed contract between the two.

## Choice
Option 3.
- **Python:** anything that writes a base table (audited), parses files, fits curves, applies assay QC, picks the
  reportable run, tampers (INJ-7), or verifies hashes.
- **dbt SQL:** custody status and flags, ALCOA+ findings, reportable fact, missing results, re-assay list, KPIs,
  scorecard. These are read-only derivations with dbt tests.
- **dbt Python model:** `mart_immunogenicity.py` only, so it can import `pipeline.stats` (scipy quantiles). It stays
  a dbt model, as AC-8.1 requires. `run_dbt` sets `PYTHONPATH` to the project root.
- **Config:** `config/qc_rules.yaml` is the single source. Python reads it. `pipeline.config.dbt_vars()` passes the
  needed keys to `dbt build --vars`. No threshold is hard-coded in SQL or Python.

## Consequences
- Seats can work in parallel: DE owns Python assay code and core models, GXP owns audit code and integrity models,
  LIA owns stats and marts. They meet only at the table contracts in DESIGN.md section 3.
- The dbt Python model is the most fragile piece (DESIGN R4). The fallback is written down there.
- dbt vars mean that running `dbt build` by hand needs `--vars`. `run.py` is the supported way to run it.
