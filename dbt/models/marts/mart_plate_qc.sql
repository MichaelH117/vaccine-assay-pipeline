-- mart_plate_qc: one row per plate (owner: LIA, US-6 / US-11). Definitions: docs/METRICS.md.
with std as (
    select plate_id,
           100.0 * avg(case when within_limits then 1.0 else 0.0 end) as std_pass_pct
    from {{ ref('stg_std_recovery') }}
    group by plate_id
),
ctrl as (
    select plate_id,
           max(case when ctrl_level = 'HIGH' then mean_conc end) as ctrl_high_conc,
           max(case when ctrl_level = 'LOW' then mean_conc end) as ctrl_low_conc
    from {{ ref('stg_control_results') }}
    group by plate_id
),
blank as (
    -- raw OD of the blank wells (blank-corrected blanks are 0 by construction)
    select w.plate_id, avg(w.od) as mean_blank_od
    from {{ ref('stg_well_reads') }} w
    join {{ ref('stg_plate_map') }} m on m.plate_id = w.plate_id and m.well = w.well
    where m.well_type = 'BLANK'
    group by w.plate_id
)
select
    s.plate_id,
    s.status,
    coalesce(s.reject_reasons, '') as reject_reasons,
    s.run_at,
    r.repeat_of_plate_id,
    f.converged,
    f.r_squared,
    std.std_pass_pct,
    ctrl.ctrl_high_conc,
    ctrl.ctrl_low_conc,
    blank.mean_blank_od,
    f.lloq_conc,
    f.uloq_conc,
    -- 4PL parameters (ADR 004) so the dashboard's curve gallery can draw each plate's fitted curve
    f.a as fit_a,
    f.b as fit_b,
    f.c as fit_c,
    f.d as fit_d
from {{ ref('stg_plate_status') }} s
left join {{ ref('stg_plate_runs') }} r on r.plate_id = s.plate_id
left join {{ ref('stg_curve_fits') }} f on f.plate_id = s.plate_id
left join std on std.plate_id = s.plate_id
left join ctrl on ctrl.plate_id = s.plate_id
left join blank on blank.plate_id = s.plate_id
