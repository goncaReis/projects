select i.*,
    o.customer_id, o.customer_version_id, o.order_date, o.order_status,
    o.order_id is not null as has_order_context,
    i.shipping_limit_date::date as shipping_date,
    p.version_id as product_version_id, s.version_id as seller_version_id
from {{ ref('order_items_current') }} i
left join {{ ref('int_order_context') }} o using (order_id)
left join {{ ref('products_history') }} p on i.product_id = p.product_id
    and i.dimension_observed_at >= p.valid_from
    and (i.dimension_observed_at < p.valid_to or p.valid_to is null)
left join {{ ref('resellers_history') }} s on i.seller_id = s.seller_id
    and i.dimension_observed_at >= s.valid_from
    and (i.dimension_observed_at < s.valid_to or s.valid_to is null)
