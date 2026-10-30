-- Staging: lims.samples, typed 1:1 (no logic).
select
    cast(sample_id as varchar) as sample_id,
    cast(subject_id as varchar) as subject_id,
    cast(visit as varchar) as visit,
    cast(visit_day as integer) as visit_day,
    cast(collected_at as timestamp) as collected_at
from {{ source('lims', 'samples') }}
