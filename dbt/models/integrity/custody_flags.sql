-- Chain-of-custody flags (AC-2.3 to AC-2.5). Owner: GxP seat. Grain: one row per (flag_code, key).
--   CUSTODY_GAP           a step has no event although a later step was recorded; detail names the missing
--                         step(s)                                                                key: sample_id
--   CUSTODY_ORDER         the FIRST occurrence of a step was performed before the first occurrence of an
--                         earlier step. First occurrence only, so repeat-run `assayed` events after `stored`
--                         are not flagged (DESIGN R8, ADR 006)                                    key: sample_id
--   FREEZE_THAW_EXCEEDED  aliquot freeze_thaw_count > var('max_freeze_thaw')                       key: aliquot_id
with step_order as (
    select * from (values
    {%- for s in var('custody_steps') %}
        ('{{ s }}', {{ loop.index }}){% if not loop.last %},{% endif %}
    {%- endfor %}
    ) as t(step, step_order)
),

firsts as (
    select e.sample_id, e.step, o.step_order, min(e.performed_at) as first_at
    from {{ ref('stg_custody_events') }} as e
    inner join step_order as o on o.step = e.step
    group by e.sample_id, e.step, o.step_order
),

reached as (
    select sample_id, max(step_order) as max_order
    from firsts
    group by sample_id
),

gaps as (
    select r.sample_id, string_agg(o.step, ',' order by o.step_order) as missing
    from reached as r
    inner join step_order as o on o.step_order < r.max_order
    where not exists (
        select 1 from firsts as f where f.sample_id = r.sample_id and f.step = o.step
    )
    group by r.sample_id
),

ordered as (
    select
        sample_id,
        step,
        step_order,
        first_at,
        max(first_at) over (
            partition by sample_id order by step_order rows between unbounded preceding and 1 preceding
        ) as latest_earlier_at
    from firsts
),

out_of_order as (
    select sample_id, string_agg(step, ',' order by step_order) as steps
    from ordered
    where first_at < latest_earlier_at
    group by sample_id
)

select
    'CUSTODY_GAP' as flag_code,
    'sample_id' as key_type,
    sample_id as key,
    'missing step: ' || missing as detail
from gaps

union all

select
    'CUSTODY_ORDER',
    'sample_id',
    sample_id,
    'performed before an earlier step: ' || steps
from out_of_order

union all

select
    'FREEZE_THAW_EXCEEDED',
    'aliquot_id',
    aliquot_id,
    'freeze_thaw_count ' || freeze_thaw_count || ' > limit {{ var("max_freeze_thaw") }}'
from {{ ref('stg_aliquots') }}
where freeze_thaw_count > {{ var('max_freeze_thaw') }}
