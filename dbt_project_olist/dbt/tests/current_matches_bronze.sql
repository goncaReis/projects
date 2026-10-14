select 'customers' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('customers_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='customers') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'orders' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('orders_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='orders') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'order_items' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('order_items_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='order_items') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'order_payments' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('order_payments_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='order_payments') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'order_reviews' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('order_reviews_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='order_reviews') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'products' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('products_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='products') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'resellers' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('resellers_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='resellers') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
union all
select 'geolocation' as dataset, coalesce(s.business_key,b.business_key) as business_key
from {{ ref('geolocation_current') }} s
full outer join (select business_key,row_hash from {{ source('bronze','current_rows') }}
where dataset='geolocation') b using (business_key)
where s.business_key is null or b.business_key is null or s.row_hash<>b.row_hash
