select r.*, o.customer_id, o.customer_version_id, o.order_date, o.order_status,
    o.order_id is not null as has_order_context,
    r.review_creation_date::date as review_date,
    r.review_answer_timestamp::date as review_answer_date
from {{ ref('order_reviews_current') }} r
left join {{ ref('int_order_context') }} o using (order_id)
