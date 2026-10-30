-- Staging: assay.qc_flags, typed 1:1 (no logic).
select
    cast(flag_id as varchar) as flag_id,
    cast(level as varchar) as level,
    cast(plate_id as varchar) as plate_id,
    cast(sample_id as varchar) as sample_id,
    cast(rule_id as varchar) as rule_id,
    cast(rule_version as varchar) as rule_version,
    cast(measured_value as double) as measured_value,
    cast(threshold as varchar) as threshold,
    cast(blocking as boolean) as blocking,
    cast(message as varchar) as message
from {{ source('assay', 'qc_flags') }}
