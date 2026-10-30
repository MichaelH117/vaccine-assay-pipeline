-- One row per sample: where the tube is now, and whether every configured custody step is recorded (AC-2.2).
-- Step list and order come from var('custody_steps') (config/qc_rules.yaml custody.steps). Owner: GxP seat.
--   current_step     step of the most recent event (by performed_at; ties broken by step order)
--   custody_complete true when every configured step has at least one event
--   missing_steps    comma list of configured steps with no event ('' when complete)
with step_order as (
    select * from (values
    {%- for s in var('custody_steps') %}
        ('{{ s }}', {{ loop.index }}){% if not loop.last %},{% endif %}
    {%- endfor %}
    ) as t(step, step_order)
),

samples as (
    select sample_id from {{ ref('stg_samples') }}
),

events as (
    select e.sample_id, e.step, o.step_order, e.performed_at, e.event_id
    from {{ ref('stg_custody_events') }} as e
    inner join step_order as o on o.step = e.step
),

latest as (
    select sample_id, step as current_step, performed_at as current_step_at
    from events
    qualify row_number() over (
        partition by sample_id order by performed_at desc, step_order desc, event_id desc
    ) = 1
),

absent as (
    select s.sample_id, o.step, o.step_order
    from samples as s
    cross join step_order as o
    where not exists (
        select 1 from events as e where e.sample_id = s.sample_id and e.step = o.step
    )
),

missing as (
    select sample_id, string_agg(step, ',' order by step_order) as missing_steps
    from absent
    group by sample_id
)

select
    s.sample_id,
    l.current_step,
    l.current_step_at,
    m.sample_id is null as custody_complete,
    coalesce(m.missing_steps, '') as missing_steps
from samples as s
left join latest as l on l.sample_id = s.sample_id
left join missing as m on m.sample_id = s.sample_id
