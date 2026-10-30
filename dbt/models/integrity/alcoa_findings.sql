-- ALCOA+ findings, one row per finding (AC-3.4). Owner: GxP seat.
--   ALCOA-A1  Attributable     NO_PERFORMER   custody event with null/blank performed_by            key: event_id
--   ALCOA-A2  Attributable     UNKNOWN_USER   performed_by not in lims.users                        key: event_id
--   ALCOA-C1  Contemporaneous  LATE_ENTRY     recorded_at > performed_at + var('late_entry_hours')  key: event_id
--   ALCOA-O1  Original         HASH_MISMATCH  latest re-hash of a raw plate file != stored sha256   key: plate_id
--   ALCOA-O2  Original         RECORD_MISMATCH a live lims/assay row differs from, lacks, or lost its INSERT audit
--                                             row (audit.record_reconciliation, latest run; BUG-005)  key: table key
--   ALCOA-CM1 Complete         CUSTODY_GAP    expected custody step missing (from custody_flags)    key: sample_id
-- The audit hash chain (Original / Enduring) is reported from audit.chain_verify by the scorecard, not here.
with events as (
    select * from {{ ref('stg_custody_events') }}
),

users as (
    select user_id from {{ ref('stg_users') }}
),

latest_file_check as (
    select *
    from {{ ref('stg_file_integrity') }}
    qualify row_number() over (partition by file_name order by checked_at desc) = 1
),

latest_reconciliation as (
    select *
    from {{ source('gxp_audit', 'record_reconciliation') }}
    where
        issue <> 'RUN'
        and checked_at = (select max(checked_at) from {{ source('gxp_audit', 'record_reconciliation') }})
),

findings as (
    select
        'ALCOA-A1' as rule_id,
        'Attributable' as attribute,
        'NO_PERFORMER' as flag_code,
        'event_id' as key_type,
        event_id as key,
        'custody step ' || step || ' has no performed_by' as detail,
        cast(null as varchar) as src
    from events
    where performed_by is null or trim(performed_by) = ''

    union all

    select
        'ALCOA-A2', 'Attributable', 'UNKNOWN_USER', 'event_id', e.event_id,
        'performed_by ' || e.performed_by || ' is not in lims.users',
        null
    from events as e
    where
        e.performed_by is not null
        and trim(e.performed_by) <> ''
        and not exists (select 1 from users as u where u.user_id = e.performed_by)

    union all

    select
        'ALCOA-C1', 'Contemporaneous', 'LATE_ENTRY', 'event_id', event_id,
        'recorded ' || round(date_diff('second', performed_at, recorded_at) / 3600.0, 1)
        || 'h after performed (limit {{ var("late_entry_hours") }}h)',
        null
    from events
    where date_diff('second', performed_at, recorded_at) > {{ var('late_entry_hours') }} * 3600

    union all

    select
        'ALCOA-O1', 'Original', 'HASH_MISMATCH', 'plate_id', coalesce(plate_id, file_name),
        file_name || ': stored sha256 ' || coalesce(left(stored_sha256, 12), 'null')
        || ', current ' || coalesce(left(current_sha256, 12), 'file missing'),
        null
    from latest_file_check
    where not matches

    union all

    select
        'ALCOA-O2', 'Original', 'RECORD_MISMATCH', coalesce(key_type, 'table'), coalesce(record_key, table_name),
        table_name || ' ' || issue || ': ' || coalesce(detail, ''),
        table_name
    from latest_reconciliation

    union all

    select 'ALCOA-CM1', 'Complete', 'CUSTODY_GAP', key_type, key, detail, null
    from {{ ref('custody_flags') }}
    where flag_code = 'CUSTODY_GAP'
)

select
    rule_id || ':' || key || coalesce(':' || src, '') as finding_id,
    rule_id,
    attribute,
    flag_code,
    key_type,
    key,
    detail
from findings
