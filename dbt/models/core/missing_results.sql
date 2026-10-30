-- Every LIMS sample with no reportable result, with a reason code (AC-7.4): nothing is dropped silently.
-- A sample is in exactly one of fct_reportable_result or missing_results.
with sample_flags as (
    select
        sample_id,
        bool_or(rule_id = 'ID_MISMATCH') as has_id_mismatch,
        bool_or(rule_id in ('DUP_CV', 'ABOVE_ULOQ')) as has_reassay_flag
    from {{ ref('stg_qc_flags') }}
    where sample_id is not null and blocking
    group by sample_id
)

select
    s.sample_id,
    s.subject_id,
    s.visit,
    case
        when coalesce(sel.n_runs, 0) = 0 then 'NOT_ASSAYED'
        when f.has_id_mismatch then 'ID_MISMATCH_UNRESOLVED'
        when f.has_reassay_flag then 'REASSAY_PENDING'
        when sel.reason like '%(INGEST_ERROR)%' then 'PLATE_INGEST_ERROR'
        else 'PLATE_REJECTED'
    end as reason,
    sel.reason as detail,
    coalesce(sel.n_runs, 0) as n_runs
from {{ ref('stg_samples') }} as s
left join {{ ref('stg_reportable_selection') }} as sel on s.sample_id = sel.sample_id
left join sample_flags as f on s.sample_id = f.sample_id
where s.sample_id not in (select sample_id from {{ ref('fct_reportable_result') }})
