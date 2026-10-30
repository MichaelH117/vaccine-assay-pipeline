-- Staging: audit.chain_verify, typed 1:1 (no logic).
select
    cast(verified_at as timestamp) as verified_at,
    cast(ok as boolean) as ok,
    cast(rows_checked as bigint) as rows_checked,
    cast(first_broken_seq as bigint) as first_broken_seq,
    cast(broken_table_name as varchar) as broken_table_name,
    cast(broken_record_key as varchar) as broken_record_key
from {{ source('audit', 'chain_verify') }}
