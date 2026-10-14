{{ config(materialized='view') }}
select * from {{ ref('resellers_history') }} where is_current
