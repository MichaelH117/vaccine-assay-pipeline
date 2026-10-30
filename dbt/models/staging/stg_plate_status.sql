-- Staging: assay.plate_status, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(status as varchar) as status,
    cast(reject_reasons as varchar) as reject_reasons,
    cast(run_at as timestamp) as run_at
from {{ source('assay', 'plate_status') }}
