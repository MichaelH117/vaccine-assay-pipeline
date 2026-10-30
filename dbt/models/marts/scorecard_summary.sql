-- scorecard_summary: the one headline for the demo, 1 row (owner: LIA, US-10). README and results.json read this.
-- Counting rules (METRICS.md section 4):
--   * The unit is the PROBLEM (problem_id). A problem with several keys (the INJ-2 swap has 2 sample keys) counts once,
--     and is detected only when every key is detected. Keys are reported alongside, never as the headline.
--   * "Required" problems are the INJ types in var required_inj_types (default INJ-1..INJ-8, AC-10.2); recall on them
--     must be 100%. Every other planted type (INJ-9, INJ-10 behind --optional-problems, or a new GXP injection) is
--     "optional": counted in its own columns and in the all-problems total, never hidden.
{%- set required = var('required_inj_types', ['INJ-1', 'INJ-2', 'INJ-3', 'INJ-4', 'INJ-5', 'INJ-6', 'INJ-7', 'INJ-8']) %}
with problems as (
    select problem_id,
           any_value(inj_type) as inj_type,
           bool_and(detected) as detected,
           count(*) as n_keys,
           count(*) filter (where detected) as n_keys_detected
    from {{ ref('detection_scorecard') }}
    group by problem_id
),
p as (
    select *, inj_type in ({% for t in required %}'{{ t }}'{% if not loop.last %}, {% endif %}{% endfor %}) as required
    from problems
)
select
    count(*) as problems_planted,
    count(*) filter (where detected) as problems_detected,
    sum(n_keys)::bigint as keys_planted,
    sum(n_keys_detected)::bigint as keys_detected,
    count(*) filter (where required) as required_problems_planted,
    count(*) filter (where required and detected) as required_problems_detected,
    count(distinct inj_type) filter (where required) as required_inj_types_planted,
    {{ required | length }} as required_inj_types_expected,
    count(*) filter (where not required) as optional_problems_planted,
    count(*) filter (where not required and detected) as optional_problems_detected,
    100.0 * count(*) filter (where required and detected) / nullif(count(*) filter (where required), 0)
        as required_recall_pct,
    coalesce(string_agg(problem_id, ',' order by problem_id) filter (where not detected), '') as missed_problem_ids,
    format('{} of {} required planted problems caught ({} of {} affected records); {} of {} optional',
           count(*) filter (where required and detected), count(*) filter (where required),
           coalesce(sum(n_keys_detected) filter (where required), 0), coalesce(sum(n_keys) filter (where required), 0),
           count(*) filter (where not required and detected), count(*) filter (where not required)) as headline
from p
