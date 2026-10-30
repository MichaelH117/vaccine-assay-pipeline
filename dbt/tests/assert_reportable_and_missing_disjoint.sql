-- Every LIMS sample is in exactly one of core.fct_reportable_result or core.missing_results (AC-7.4).
select s.sample_id
from {{ ref('stg_samples') }} as s
left join {{ ref('fct_reportable_result') }} as f on s.sample_id = f.sample_id
left join {{ ref('missing_results') }} as m on s.sample_id = m.sample_id
where (f.sample_id is null) = (m.sample_id is null)
