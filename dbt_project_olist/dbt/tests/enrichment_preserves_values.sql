-- Check every fact row, not just totals that could mask offsetting errors.
select 'items' as model, i.business_key
from {{ ref('order_items_current') }} i join {{ ref('fct_order_items') }} f using(business_key)
where (i.price,i.freight_value) is distinct from (f.price,f.freight_value)
union all
select 'payments', p.business_key
from {{ ref('order_payments_current') }} p join {{ ref('fct_payments') }} f using(business_key)
where (p.payment_value,p.payment_installments) is distinct from (f.payment_value,f.payment_installments)
union all
select 'reviews', r.business_key
from {{ ref('order_reviews_current') }} r join {{ ref('fct_reviews') }} f using(business_key)
where r.review_score is distinct from f.review_score
