select 'fct_order_items' as model, f.business_key
from {{ ref('fct_order_items') }} f join {{ ref('int_order_context') }} o using(order_id)
where (f.customer_version_id,f.customer_id,f.order_date,f.order_status)
is distinct from (o.customer_version_id,o.customer_id,o.order_date,o.order_status)
union all
select 'fct_payments' as model, f.business_key
from {{ ref('fct_payments') }} f join {{ ref('int_order_context') }} o using(order_id)
where (f.customer_version_id,f.customer_id,f.order_date,f.order_status)
is distinct from (o.customer_version_id,o.customer_id,o.order_date,o.order_status)
union all
select 'fct_reviews' as model, f.business_key
from {{ ref('fct_reviews') }} f join {{ ref('int_order_context') }} o using(order_id)
where (f.customer_version_id,f.customer_id,f.order_date,f.order_status)
is distinct from (o.customer_version_id,o.customer_id,o.order_date,o.order_status)
