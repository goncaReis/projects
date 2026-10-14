{{ config(materialized='view') }}
select * from {{ ref('customers_history') }} where is_current
