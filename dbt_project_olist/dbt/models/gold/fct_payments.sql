select p.*, o.customer_id, o.customer_version_id, o.order_date, o.order_status,
    o.order_id is not null as has_order_context
from {{ ref('order_payments_current') }} p
left join {{ ref('int_order_context') }} o using (order_id)
