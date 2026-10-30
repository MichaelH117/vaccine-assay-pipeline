-- Staging: assay.ingest_errors, typed 1:1 (no logic).
select
    cast(file_name as varchar) as file_name,
    cast(error as varchar) as error,
    cast(logged_at as timestamp) as logged_at
from {{ source('assay', 'ingest_errors') }}
