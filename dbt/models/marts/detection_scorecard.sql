-- detection_scorecard: one row per injected key (owner: LIA, US-10). Only the scorecard marts and tests read truth.*.
-- A key is detected when an accepted flag for its INJ type (var expected_flags, from scorecard.expected_flags in
-- config/qc_rules.yaml) sits on the same key_type + key, AND the key carries none of that INJ type's masking flags.
-- Masking flags (REVIEW F3): a broken curve also produces CTRL_OOR, so INJ-5 ("control off, curve fine") only counts
-- when the plate has no FIT_FAIL / STD_RECOVERY. Otherwise the plate was rejected for a different reason and the
-- control rule is not proven. An INJ type with no expected_flags entry is never detected (a loud miss, by design).
-- A problem is detected only when all of its keys are detected (problem_detected).
{%- set masking = var('masking_flags', {'INJ-5': ['FIT_FAIL', 'STD_RECOVERY']}) %}
with all_flags as (
    select rule_id as flag_code,
           case when level = 'PLATE' then 'plate_id' else 'sample_id' end as key_type,
           case when level = 'PLATE' then plate_id else sample_id end as key
    from {{ ref('stg_qc_flags') }}
    union all
    select flag_code, key_type, key from {{ ref('custody_flags') }}
    union all
    select flag_code, key_type, key from {{ ref('alcoa_findings') }}
    union all
    select 'AUDIT_CHAIN_BROKEN', 'event_id', broken_record_key
    from {{ ref('stg_chain_verify') }}
    where not ok and broken_record_key is not null
),
expected as (
    select inj_type, flag_code from {{ ref('scorecard_expected_flags') }}
),
masking as (
    select * from (values
        ('', '')
    {%- for inj, flags in masking.items() %}
    {%- for f in flags %},
        ('{{ inj }}', '{{ f }}')
    {%- endfor %}
    {%- endfor %}
    ) as t(inj_type, flag_code)
    where inj_type <> ''
),
truth as (
    select problem_id, inj_type, key_type, affected_key, description
    from {{ ref('stg_injected_problems') }}
),
matched as (
    select t.problem_id, t.affected_key,
           string_agg(distinct a.flag_code, ',' order by a.flag_code) as caught_by
    from truth t
    join expected e on e.inj_type = t.inj_type
    join all_flags a on a.flag_code = e.flag_code and a.key_type = t.key_type and a.key = t.affected_key
    group by t.problem_id, t.affected_key
),
masked as (
    select t.problem_id, t.affected_key,
           string_agg(distinct a.flag_code, ',' order by a.flag_code) as masked_by
    from truth t
    join masking m on m.inj_type = t.inj_type
    join all_flags a on a.flag_code = m.flag_code and a.key_type = t.key_type and a.key = t.affected_key
    group by t.problem_id, t.affected_key
),
expected_list as (
    select inj_type, string_agg(flag_code, ',' order by flag_code) as expected_flags
    from expected group by inj_type
)
select
    t.problem_id || ':' || t.affected_key as scorecard_key,
    t.problem_id,
    t.inj_type,
    t.key_type,
    t.affected_key,
    t.description,
    el.expected_flags,
    m.caught_by is not null and mk.masked_by is null as detected,
    case when mk.masked_by is null then m.caught_by end as caught_by,
    mk.masked_by,
    bool_and(m.caught_by is not null and mk.masked_by is null) over (partition by t.problem_id) as problem_detected
from truth t
left join matched m on m.problem_id = t.problem_id and m.affected_key = t.affected_key
left join masked mk on mk.problem_id = t.problem_id and mk.affected_key = t.affected_key
left join expected_list el on el.inj_type = t.inj_type
