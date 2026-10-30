-- Re-assay requests, one row per sample x plate (AC-6.2, AC-6.4): ABOVE_ULOQ (at dilution x reassay factor), DUP_CV
-- (same dilution), and every sample mapped to a REJECTED plate, including a plate whose file could not be read
-- (INGEST_ERROR, BUG-003). A sample that read >ULOQ on a rejected plate also gets the higher dilution (review F9).
-- Several reasons on one plate are joined in rule_id. `resolved` = the sample later got a reportable result from
-- another plate.
with mapped as (
    select distinct plate_id, sample_id, dilution
    from {{ ref('stg_plate_map') }}
    where well_type = 'SAMPLE'
),

requests as (
    select sample_id, plate_id, rule_id
    from {{ ref('stg_qc_flags') }}
    where rule_id in ('ABOVE_ULOQ', 'DUP_CV')

    union all

    select m.sample_id, m.plate_id, 'PLATE_REJECTED' as rule_id
    from mapped as m
    inner join {{ ref('stg_plate_status') }} as p on m.plate_id = p.plate_id
    where p.status = 'REJECTED'
)

select
    q.sample_id,
    q.plate_id,
    string_agg(distinct q.rule_id, ',' order by q.rule_id) as rule_id,
    max(case when q.rule_id = 'ABOVE_ULOQ' or r.range_flag = '>ULOQ'
             then m.dilution * {{ var('reassay_dilution_factor') }}
             else m.dilution end) as suggested_dilution,
    coalesce(bool_or(f.plate_id is not null and f.plate_id <> q.plate_id), false) as resolved
from requests as q
inner join mapped as m on q.sample_id = m.sample_id and q.plate_id = m.plate_id
left join {{ ref('stg_sample_results') }} as r on q.sample_id = r.sample_id and q.plate_id = r.plate_id
left join {{ ref('fct_reportable_result') }} as f on q.sample_id = f.sample_id
group by q.sample_id, q.plate_id
