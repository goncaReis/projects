select 'customers' as dataset, business_key from (
  select business_key, valid_from, valid_to,
    lag(valid_to) over(partition by business_key order by valid_from) as previous_end,
    row_number() over(partition by business_key order by valid_from) as position
  from {{ ref('customers_history') }}
) h where valid_to <= valid_from or (position > 1 and (previous_end is null or previous_end > valid_from))
union all
select 'products' as dataset, business_key from (
  select business_key, valid_from, valid_to,
    lag(valid_to) over(partition by business_key order by valid_from) as previous_end,
    row_number() over(partition by business_key order by valid_from) as position
  from {{ ref('products_history') }}
) h where valid_to <= valid_from or (position > 1 and (previous_end is null or previous_end > valid_from))
union all
select 'resellers' as dataset, business_key from (
  select business_key, valid_from, valid_to,
    lag(valid_to) over(partition by business_key order by valid_from) as previous_end,
    row_number() over(partition by business_key order by valid_from) as position
  from {{ ref('resellers_history') }}
) h where valid_to <= valid_from or (position > 1 and (previous_end is null or previous_end > valid_from))
