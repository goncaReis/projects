-- Aggregating items and payments separately must not multiply order totals.
select 'items' as metric
where (select coalesce(sum(item_total),0) from {{ ref('fct_orders') }})
   <> (select coalesce(sum(i.price),0) from {{ ref('order_items_current') }} i
       join {{ ref('orders_current') }} o using (order_id))
union all
select 'payments'
where (select coalesce(sum(payment_total),0) from {{ ref('fct_orders') }})
   <> (select coalesce(sum(p.payment_value),0) from {{ ref('order_payments_current') }} p
       join {{ ref('orders_current') }} o using (order_id))
