CREATE TABLE OLIST_ECOMMERCE.RAW.raw_order_items (

    order_id VARCHAR(64),
    order_item_id tinyint,
    product_id VARCHAR(64),
    seller_id VARCHAR(64),
    shipping_limit_date datetime,
    price float,
    freight_value float
)
