-- Staging: assay.reportable_selection, typed 1:1 (no logic).
select
    cast(sample_id as varchar) as sample_id,
    cast(result_id as varchar) as result_id,
    cast(decision as varchar) as decision,
    cast(reason as varchar) as reason,
    cast(n_runs as integer) as n_runs
from {{ source('assay', 'reportable_selection') }}
