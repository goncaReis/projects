CREATE TABLE OLIST_ECOMMERCE.RAW.raw_orders(

    order_id varchar(64),
    customer_id varchar(64),
    order_status varchar(20),
    order_purchase_timestamp datetime,
    order_approved_at datetime,
    order_delivered_carrier_date datetime,
    order_delivered_customer_date datetime,
    order_estimated_delivery_date datetime
)
