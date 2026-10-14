select 'fct_orders' as model where
    (select count(*) from {{ ref('fct_orders') }}) <> (select count(*) from {{ ref('orders_current') }})
    or exists (
      (select business_key from {{ ref('fct_orders') }} except select business_key from {{ ref('orders_current') }})
      union all
      (select business_key from {{ ref('orders_current') }} except select business_key from {{ ref('fct_orders') }})
    )
union all
select 'fct_order_items' as model where
    (select count(*) from {{ ref('fct_order_items') }}) <> (select count(*) from {{ ref('order_items_current') }})
    or exists (
      (select business_key from {{ ref('fct_order_items') }} except select business_key from {{ ref('order_items_current') }})
      union all
      (select business_key from {{ ref('order_items_current') }} except select business_key from {{ ref('fct_order_items') }})
    )
union all
select 'fct_payments' as model where
    (select count(*) from {{ ref('fct_payments') }}) <> (select count(*) from {{ ref('order_payments_current') }})
    or exists (
      (select business_key from {{ ref('fct_payments') }} except select business_key from {{ ref('order_payments_current') }})
      union all
      (select business_key from {{ ref('order_payments_current') }} except select business_key from {{ ref('fct_payments') }})
    )
union all
select 'fct_reviews' as model where
    (select count(*) from {{ ref('fct_reviews') }}) <> (select count(*) from {{ ref('order_reviews_current') }})
    or exists (
      (select business_key from {{ ref('fct_reviews') }} except select business_key from {{ ref('order_reviews_current') }})
      union all
      (select business_key from {{ ref('order_reviews_current') }} except select business_key from {{ ref('fct_reviews') }})
    )
