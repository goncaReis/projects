with payments as (
    select order_id, sum(payment_value)::numeric(18,2) as payment_total
    from {{ ref('order_payments_current') }} group by order_id
), items as (
    select order_id, count(*) as item_count,
        sum(price)::numeric(18,2) as item_total,
        sum(freight_value)::numeric(18,2) as freight_total
    from {{ ref('order_items_current') }} group by order_id
)
select o.*,
    coalesce(i.item_count,0)::bigint as item_count,
    coalesce(i.item_total,0)::numeric(18,2) as item_total,
    coalesce(i.freight_total,0)::numeric(18,2) as freight_total,
    coalesce(p.payment_total,0)::numeric(18,2) as payment_total
from {{ ref('int_order_context') }} o
left join items i using (order_id)
left join payments p using (order_id)
