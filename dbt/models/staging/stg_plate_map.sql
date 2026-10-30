-- Staging: assay.plate_map, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(well as varchar) as well,
    cast(well_type as varchar) as well_type,
    cast(level as integer) as level,
    cast(nominal_conc as double) as nominal_conc,
    cast(sample_id as varchar) as sample_id,
    cast(dilution as integer) as dilution
from {{ source('assay', 'plate_map') }}
