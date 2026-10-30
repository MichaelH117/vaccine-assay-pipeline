-- Staging: audit.audit_log, typed 1:1 (no logic).
select
    cast(audit_seq as bigint) as audit_seq,
    cast(table_name as varchar) as table_name,
    cast(record_key as varchar) as record_key,
    cast(action as varchar) as action,
    cast(field as varchar) as field,
    cast(old_value as varchar) as old_value,
    cast(new_value as varchar) as new_value,
    cast(performed_by as varchar) as performed_by,
    cast(reason as varchar) as reason,
    cast(audit_ts_utc as timestamp) as audit_ts_utc,
    cast(supersedes_seq as bigint) as supersedes_seq,
    cast(prev_hash as varchar) as prev_hash,
    cast(row_hash as varchar) as row_hash
from {{ source('audit', 'audit_log') }}
