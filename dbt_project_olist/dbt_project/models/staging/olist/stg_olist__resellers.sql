{{ config(materialized='view') }}

SELECT * FROM {{ source('olist', 'olist_sellers') }}
