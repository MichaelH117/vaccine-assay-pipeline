-- Staging: lims.raw_files, typed 1:1 (no logic).
select
    cast(file_name as varchar) as file_name,
    cast(plate_id as varchar) as plate_id,
    cast(raw_path as varchar) as raw_path,
    cast(sha256 as varchar) as sha256,
    cast(ingested_at as timestamp) as ingested_at
from {{ source('lims', 'raw_files') }}
