-- Staging: lims.subjects, typed 1:1 (no logic).
select
    cast(subject_id as varchar) as subject_id,
    cast(group_name as varchar) as group_name,
    cast(site_id as varchar) as site_id
from {{ source('lims', 'subjects') }}
