-- Staging: audit.file_integrity, typed 1:1 (no logic).
select
    cast(file_name as varchar) as file_name,
    cast(plate_id as varchar) as plate_id,
    cast(stored_sha256 as varchar) as stored_sha256,
    cast(current_sha256 as varchar) as current_sha256,
    cast(matches as boolean) as matches,
    cast(checked_at as timestamp) as checked_at
from {{ source('audit', 'file_integrity') }}
