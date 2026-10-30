-- mart_lab_kpis: lab operations KPIs in long format (owner: LIA, US-9). One row per kpi_id.
-- Every KPI is defined in docs/METRICS.md; tests/test_kpis.py recomputes them from base tables (AC-9.3).
with received as (
    -- first 'received' custody event per sample
    select sample_id, min(performed_at) as received_at
    from {{ ref('stg_custody_events') }}
    where step = 'received'
    group by sample_id
),
tat as (
    select f.sample_id,
           date_diff('second', rcv.received_at, f.run_at) / 86400.0 as tat_days
    from {{ ref('fct_reportable_result') }} f
    join received rcv on rcv.sample_id = f.sample_id
    where f.run_at is not null
),
plates as (
    select count(*) as n_plates,
           count(*) filter (where status = 'REJECTED') as n_rejected
    from {{ ref('stg_plate_status') }}
),
plate_rules as (
    -- plate-level reject reasons (not thresholds); a row per reason even when its count is 0.
    -- INGEST_ERROR: an unreadable plate file is kept as REJECTED (BUG-003), BUG-012
    select * from (values ('FIT_FAIL'), ('STD_RECOVERY'), ('CTRL_OOR'), ('BLANK_HIGH'), ('INGEST_ERROR')) t(rule_id)
),
reasons as (
    select plate_id, trim(unnest(string_split(reject_reasons, ','))) as rule_id
    from {{ ref('stg_plate_status') }}
    where status = 'REJECTED' and coalesce(reject_reasons, '') <> ''
),
assayed as (
    select count(distinct sample_id) as n from {{ ref('stg_sample_results') }}
),
reassay as (
    select count(distinct sample_id) as n from {{ ref('reassay_list') }}
),
custody as (
    select count(*) as n_samples,
           count(*) filter (where custody_complete) as n_complete
    from {{ ref('v_custody_status') }}
),
alcoa as (
    select (select count(*) from {{ ref('alcoa_findings') }}) as n_findings,
           (select count(*) from {{ ref('stg_custody_events') }}) as n_records
)
select 'TAT_MEDIAN_DAYS' as kpi_id,
       'Turnaround time, received to reportable result (median)' as kpi_name,
       (select quantile_cont(tat_days, 0.5) from tat) as value,
       'days' as unit,
       cast(null as double) as numerator,
       (select count(*) from tat)::double as denominator
union all
select 'TAT_P90_DAYS', 'Turnaround time, received to reportable result (90th percentile)',
       (select quantile_cont(tat_days, 0.9) from tat), 'days',
       null, (select count(*) from tat)::double
union all
select 'PLATE_FAIL_RATE', 'Plate failure rate (rejected / total plates)',
       100.0 * n_rejected / nullif(n_plates, 0), '%', n_rejected::double, n_plates::double
from plates
union all
select 'PLATE_REJECT_' || pr.rule_id, 'Rejected plates citing ' || pr.rule_id,
       count(distinct r.plate_id)::double, 'plates', count(distinct r.plate_id)::double,
       any_value((select n_plates from plates))::double
from plate_rules pr
left join reasons r on r.rule_id = pr.rule_id
group by pr.rule_id
union all
select 'REASSAY_RATE', 'Re-assay rate (samples on the re-assay list / samples assayed)',
       100.0 * reassay.n / nullif(assayed.n, 0), '%', reassay.n::double, assayed.n::double
from reassay, assayed
union all
select 'CUSTODY_COMPLETE_PCT', 'Samples with complete chain of custody',
       100.0 * n_complete / nullif(n_samples, 0), '%', n_complete::double, n_samples::double
from custody
union all
select 'ALCOA_FINDINGS_PER_100', 'ALCOA+ findings per 100 custody event records',
       100.0 * n_findings / nullif(n_records, 0), 'per 100 records', n_findings::double, n_records::double
from alcoa
