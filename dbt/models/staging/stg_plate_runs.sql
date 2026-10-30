-- Staging: lims.plate_runs, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(run_at as timestamp) as run_at,
    cast(analyst as varchar) as analyst,
    cast(repeat_of_plate_id as varchar) as repeat_of_plate_id
from {{ source('lims', 'plate_runs') }}
