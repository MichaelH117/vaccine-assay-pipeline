-- Staging: assay.std_recovery, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(level as integer) as level,
    cast(nominal_conc as double) as nominal_conc,
    cast(mean_od as double) as mean_od,
    cast(back_calc_conc as double) as back_calc_conc,
    cast(recovery_pct as double) as recovery_pct,
    cast(within_limits as boolean) as within_limits
from {{ source('assay', 'std_recovery') }}
