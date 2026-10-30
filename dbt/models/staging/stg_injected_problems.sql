-- Staging: truth.injected_problems, typed 1:1 (no logic).
select
    cast(problem_id as varchar) as problem_id,
    cast(inj_type as varchar) as inj_type,
    cast(key_type as varchar) as key_type,
    cast(affected_key as varchar) as affected_key,
    cast(description as varchar) as description
from {{ source('truth', 'injected_problems') }}
