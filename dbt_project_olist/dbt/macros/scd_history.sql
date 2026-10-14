{% macro scd_history(dataset, columns) %}
{% set tracked = var('scd2_columns')[dataset] %}
{% for field in tracked %}
  {% if field not in columns %}{{ exceptions.raise_compiler_error('Unknown SCD2 column: ' ~ field) }}{% endif %}
{% endfor %}
with events as (
    select e.*, b.observed_at,
        jsonb_build_array(
          {% for field in tracked %}e.payload -> '{{ field }}'{% if not loop.last %}, {% endif %}{% endfor %}
        ) as tracked_values
    from {{ source('bronze', 'cdc_events') }} e
    join {{ source('bronze', 'batches') }} b using (batch_id)
    where e.dataset = '{{ dataset }}'
    {% if var('batch_id', none) is not none %}and e.batch_id <= {{ var('batch_id') | int }}{% endif %}
), compared as (
    select *, lag(tracked_values) over (partition by business_key order by batch_id) as previous_values
    from events
), boundaries as (
    -- Type 1-only updates do not end an SCD2 interval.
    select * from compared
    where operation in ('I','D') or tracked_values is distinct from previous_values
), versions as (
    select *, lead(observed_at) over (partition by business_key order by batch_id) as valid_to
    from boundaries
), latest as (
    -- Apply Type 1 corrections across ALL retained versions, including closed ones.
    select distinct on (business_key) business_key, payload, row_hash, observed_at, event_id
    from events order by business_key, batch_id desc
)
select
    v.event_id as version_id, v.business_key,
    {% for name, type in columns.items() %}
    ({{ 'v' if name in tracked else 'l' }}.payload ->> '{{ name }}')::{{ type }} as {{ name }},
    {% endfor %}
    v.observed_at as valid_from, v.valid_to, v.valid_to is null as is_current,
    v.batch_id, l.event_id as source_event_id, l.observed_at as last_observed_at,
    l.row_hash
from versions v
join latest l using (business_key)
where v.operation <> 'D'
{% endmacro %}
