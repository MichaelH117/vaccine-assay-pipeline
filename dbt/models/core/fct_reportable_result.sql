-- One reportable result per sample (AC-7.1). The run was chosen in Python (pipeline/reportable.py, ADR 006): the
-- latest run on an ACCEPTED plate with no blocking flag. Below-LLOQ rule (ADR 003): a result is <LLOQ when its signal
-- is below the plate working range OR its concentration is below the fixed assay LLOQ; its analysis value is then
-- lloq_impute_factor x assay LLOQ (AC-7.3).
with sel as (
    select sample_id, result_id, reason
    from {{ ref('stg_reportable_selection') }}
    where decision = 'REPORTABLE'
),

res as (
    select
        r.*,
        coalesce(r.range_flag = '<LLOQ' or r.conc_au_ml < {{ var('assay_lloq_au_ml') }}, false) as below_lloq
    from {{ ref('stg_sample_results') }} as r
)

select
    s.sample_id,
    s.subject_id,
    sub.group_name,
    s.visit,
    s.visit_day,
    res.result_id,
    res.plate_id,
    res.run_at,
    res.dilution,
    case when res.below_lloq then '<LLOQ' else printf('%.2f', res.conc_au_ml) end as reported_value,
    case when res.below_lloq then null else res.conc_au_ml end as conc_au_ml,
    case
        when res.below_lloq then {{ var('lloq_impute_factor') }} * {{ var('assay_lloq_au_ml') }}
        else res.conc_au_ml
    end as analysis_value_au_ml,
    res.below_lloq,
    sel.reason as selection_reason
from sel
inner join res on sel.result_id = res.result_id
inner join {{ ref('stg_samples') }} as s on sel.sample_id = s.sample_id
inner join {{ ref('stg_subjects') }} as sub on s.subject_id = sub.subject_id
