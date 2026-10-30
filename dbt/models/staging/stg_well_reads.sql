-- Staging: assay.well_reads, typed 1:1 (no logic).
select
    cast(plate_id as varchar) as plate_id,
    cast(well as varchar) as well,
    cast(row_letter as varchar) as row_letter,
    cast(col_num as integer) as col_num,
    cast(od as double) as od,
    cast(od_blank_corrected as double) as od_blank_corrected
from {{ source('assay', 'well_reads') }}
