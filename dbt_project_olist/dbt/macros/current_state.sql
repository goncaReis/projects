{% macro current_state(dataset, columns, binding_columns=[]) %}
with events as (
    select e.*, b.observed_at,
        {% if binding_columns %}
        jsonb_build_array({% for field in binding_columns %}e.payload -> '{{ field }}'{% if not loop.last %}, {% endif %}{% endfor %})
        {% else %}'[]'::jsonb{% endif %} as binding
    from {{ source('bronze','cdc_events') }} e
    join {{ source('bronze','batches') }} b using (batch_id)
    where e.dataset = '{{ dataset }}'
    {% if var('batch_id', none) is not none %}and e.batch_id <= {{ var('batch_id') | int }}{% endif %}
), compared as (
    select *, lag(binding) over (partition by business_key order by batch_id) as previous_binding
    from events
), attributed as (
    select *,
        max(case when operation='I' or (operation='U' and binding is distinct from previous_binding)
            then observed_at end) over (partition by business_key order by batch_id) as dimension_observed_at
    from compared
), latest as (
    select distinct on (business_key) * from attributed order by business_key,batch_id desc
)
select event_id as source_event_id, business_key,
    {% for name, type in columns.items() %}
    (payload ->> '{{ name }}')::{{ type }} as {{ name }},
    {% endfor %}
    dimension_observed_at, observed_at as last_observed_at, batch_id, row_hash
from latest where operation <> 'D'
{% endmacro %}
