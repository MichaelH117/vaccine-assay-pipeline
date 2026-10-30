-- scorecard_false_positives: 1 row (owner: LIA, AC-10.3, REVIEW F2 + F7).
-- Sample level: a sample-level flag is a blocking SAMPLE flag in qc_flags (DUP_CV, ABOVE_ULOQ, ID_MISMATCH;
-- BELOW_LLOQ is a normal result), or a custody / ALCOA+ flag keyed on the sample, one of its aliquots or one of its
-- custody events. A (sample, flag) pair is "explained" only when an injected key linked to that sample (the sample,
-- an aliquot or an event) has an INJ type whose expected_flags include that flag code. A planted sample-level problem
-- explains the same flag on any plate that sample ran on (accepted cross-plate match, METRICS.md section 4).
-- Plate level: a REJECTED plate is unexplained when it is not an injected plate_id key. A false reject removes about
-- 37 samples from reporting, so it is reported separately from the sample rate.
with samples as (
    select sample_id from {{ ref('stg_samples') }}
),
sample_keys as (
    select sample_id, 'sample_id' as key_type, sample_id as key from samples
    union all
    select sample_id, 'aliquot_id', aliquot_id from {{ ref('stg_aliquots') }}
    union all
    select sample_id, 'event_id', event_id from {{ ref('stg_custody_events') }}
),
flags as (
    select rule_id as flag_code, 'sample_id' as key_type, sample_id as key
    from {{ ref('stg_qc_flags') }}
    where level = 'SAMPLE' and blocking
    union all
    select flag_code, key_type, key from {{ ref('custody_flags') }}
    union all
    select flag_code, key_type, key from {{ ref('alcoa_findings') }}
),
flagged as (
    select distinct sk.sample_id, f.flag_code
    from flags f
    join sample_keys sk on sk.key_type = f.key_type and sk.key = f.key
),
explained as (
    select distinct sk.sample_id, e.flag_code
    from {{ ref('stg_injected_problems') }} t
    join sample_keys sk on sk.key_type = t.key_type and sk.key = t.affected_key
    join {{ ref('scorecard_expected_flags') }} e on e.inj_type = t.inj_type
),
unexplained_samples as (
    select distinct f.sample_id
    from flagged f
    left join explained x on x.sample_id = f.sample_id and x.flag_code = f.flag_code
    where x.sample_id is null
),
plates as (
    select plate_id, status from {{ ref('stg_plate_status') }}
),
injected_plates as (
    select distinct affected_key as plate_id
    from {{ ref('stg_injected_problems') }}
    where key_type = 'plate_id'
),
unexplained_plates as (
    select p.plate_id
    from plates p
    where p.status = 'REJECTED' and p.plate_id not in (select plate_id from injected_plates)
)
select
    (select count(*) from samples) as samples_total,
    (select count(*) from unexplained_samples) as samples_with_unexplained_flag,
    100.0 * (select count(*) from unexplained_samples) / nullif((select count(*) from samples), 0) as fp_pct,
    (select count(*) from plates) as plates_total,
    (select count(*) from plates where status = 'REJECTED') as plates_rejected,
    (select count(*) from unexplained_plates) as plates_rejected_unexplained,
    100.0 * (select count(*) from unexplained_plates) / nullif((select count(*) from plates), 0) as plate_fp_pct,
    coalesce((select string_agg(plate_id, ',' order by plate_id) from unexplained_plates), '')
        as unexplained_plate_ids
