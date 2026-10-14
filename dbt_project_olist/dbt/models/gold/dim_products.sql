select p.*, t.product_category_name_english
from {{ ref('products_history') }} p
left join {{ ref('product_category_name_translation') }} t using (product_category_name)
