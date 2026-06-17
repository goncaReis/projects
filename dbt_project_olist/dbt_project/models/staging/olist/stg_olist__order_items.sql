{{ config(materialized='view') }}

SELECT * FROM {{ source('olist', 'olist_order_items') }}
