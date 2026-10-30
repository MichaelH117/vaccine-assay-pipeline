-- Staging: lims.custody_events, typed 1:1 (no logic).
select
    cast(event_id as varchar) as event_id,
    cast(sample_id as varchar) as sample_id,
    cast(aliquot_id as varchar) as aliquot_id,
    cast(step as varchar) as step,
    cast(performed_by as varchar) as performed_by,
    cast(performed_at as timestamp) as performed_at,
    cast(recorded_at as timestamp) as recorded_at,
    cast(location as varchar) as location,
    cast(plate_id as varchar) as plate_id,
    cast(well as varchar) as well,
    cast(reason as varchar) as reason
from {{ source('lims', 'custody_events') }}
