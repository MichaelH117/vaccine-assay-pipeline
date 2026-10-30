-- Staging: assay.sample_results, typed 1:1 (no logic).
select
    cast(result_id as varchar) as result_id,
    cast(plate_id as varchar) as plate_id,
    cast(sample_id as varchar) as sample_id,
    cast(dilution as integer) as dilution,
    cast(mean_od as double) as mean_od,
    cast(od_cv_pct as double) as od_cv_pct,
    cast(range_flag as varchar) as range_flag,
    cast(conc_au_ml as double) as conc_au_ml,
    cast(run_at as timestamp) as run_at
from {{ source('assay', 'sample_results') }}
