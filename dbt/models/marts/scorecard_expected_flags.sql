-- scorecard_expected_flags: the accepted flag codes per INJ type, one row per (inj_type, flag_code) (owner: LIA).
-- Straight from var expected_flags (config scorecard.expected_flags), so both scorecard marts share one list.
-- A new planted problem type (for example a GXP direct-edit injection) only needs a config entry here.
select * from (values
{%- for inj, flags in var('expected_flags').items() %}
{%- set outer = loop %}
{%- for f in flags %}
    ('{{ inj }}', '{{ f }}'){% if not (outer.last and loop.last) %},{% endif %}
{%- endfor %}
{%- endfor %}
) as t(inj_type, flag_code)
