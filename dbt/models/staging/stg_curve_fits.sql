-- Staging: assay.curve_fits, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(a as double) as a,
    cast(b as double) as b,
    cast(c as double) as c,
    cast(d as double) as d,
    cast(r_squared as double) as r_squared,
    cast(converged as boolean) as converged,
    cast(fit_message as varchar) as fit_message,
    cast(n_points as integer) as n_points,
    cast(lloq_conc as double) as lloq_conc,
    cast(uloq_conc as double) as uloq_conc,
    cast(lloq_od as double) as lloq_od,
    cast(uloq_od as double) as uloq_od
from {{ source('assay', 'curve_fits') }}
