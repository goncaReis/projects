select distinct order_status
from {{ ref('orders_current') }} where order_status is not null
