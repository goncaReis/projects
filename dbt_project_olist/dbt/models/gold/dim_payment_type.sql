select distinct payment_type
from {{ ref('order_payments_current') }} where payment_type is not null
