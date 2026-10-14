-- One row per order. Customer attribution is shared by every order-related fact.
select o.*, o.order_purchase_timestamp::date as order_date,
    o.order_approved_at::date as approved_date,
    o.order_delivered_carrier_date::date as carrier_date,
    o.order_delivered_customer_date::date as delivered_date,
    o.order_estimated_delivery_date::date as estimated_delivery_date,
    c.version_id as customer_version_id
from {{ ref('orders_current') }} o
left join {{ ref('customers_history') }} c
    on o.customer_id = c.customer_id
    and o.dimension_observed_at >= c.valid_from
    and (o.dimension_observed_at < c.valid_to or c.valid_to is null)
