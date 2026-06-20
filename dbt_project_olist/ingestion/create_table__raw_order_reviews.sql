CREATE TABLE OLIST_ECOMMERCE.RAW.raw_order_reviews(

    review_id varchar(64),
    order_id varchar(64),
    review_score tinyint,
    review_comment_title STRING,
    review_comment_message STRING,
    review_creation_date datetime,
    review_answer_timestamp datetime
)
