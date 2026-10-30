-- Staging: assay.control_results, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(ctrl_level as varchar) as ctrl_level,
    cast(mean_conc as double) as mean_conc,
    cast(target_conc as double) as target_conc,
    cast(low_limit as double) as low_limit,
    cast(high_limit as double) as high_limit
from {{ source('assay', 'control_results') }}
