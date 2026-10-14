select order_date,
    count(*) as order_count,
    sum(item_count)::bigint as item_count,
    sum(item_total)::numeric(18,2) as item_total,
    sum(freight_total)::numeric(18,2) as freight_total,
    sum(payment_total)::numeric(18,2) as payment_total
from {{ ref('fct_orders') }} group by order_date
