CREATE TABLE OLIST_ECOMMERCE.RAW.raw_order_payments (

    order_id varchar(64),
    payment_sequential tinyint,
    payment_type varchar(30),
    payment_installments tinyint,
    payment_value float
)