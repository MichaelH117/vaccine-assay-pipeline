-- Staging: lims.users, typed 1:1 (no logic).
select
    cast(user_id as varchar) as user_id,
    cast(display_name as varchar) as display_name,
    cast(role as varchar) as role,
    cast(active as boolean) as active
from {{ source('lims', 'users') }}
