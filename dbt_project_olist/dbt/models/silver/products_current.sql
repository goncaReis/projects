{{ config(materialized='view') }}
select * from {{ ref('products_history') }} where is_current
