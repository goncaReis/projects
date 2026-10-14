{{ config(severity='warn') }}
-- Preserve unmatched facts and surface them instead of dropping or inventing attribution.
select 'orders' as model, business_key from {{ ref('fct_orders') }} where customer_version_id is null
union all
select 'items', business_key from {{ ref('fct_order_items') }}
where not has_order_context or customer_version_id is null or product_version_id is null or seller_version_id is null
union all
select 'payments', business_key from {{ ref('fct_payments') }}
where not has_order_context or customer_version_id is null
union all
select 'reviews', business_key from {{ ref('fct_reviews') }}
where not has_order_context or customer_version_id is null
