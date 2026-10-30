-- Staging: lims.aliquots, typed 1:1 (no logic).
select
    cast(aliquot_id as varchar) as aliquot_id,
    cast(sample_id as varchar) as sample_id,
    cast(created_at as timestamp) as created_at,
    cast(freeze_thaw_count as integer) as freeze_thaw_count
from {{ source('lims', 'aliquots') }}
