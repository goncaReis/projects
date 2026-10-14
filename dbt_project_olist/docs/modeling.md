# Dimensional model and change policy

## Business questions and fact grains

| Gold table | Grain | Example use |
|---|---|---|
| fct_orders | One current order | Order count, fulfillment dates, order totals |
| fct_order_items | One order_id + order_item_id | Item sales, freight, product/seller analysis |
| fct_payments | One order_id + payment_sequential | Payment value, method and installments |
| fct_reviews | One review_id + order_id | Review scores and responses |
| daily_sales | One purchase date | Date-level volume and amount summaries |

Order facts retain orders without items. Item sales and payments are different
measures and may differ. Reviews are associated with orders; no allocation to
individual products or sellers is claimed.

## Conformed dimensions and enrichment

`dim_customers`, `dim_products` and `dim_sellers` expose SCD2 version keys.
`dim_order_status` and `dim_payment_type` use their unique text values as keys.
A calendar dimension is defined in Power BI; gold facts expose date-only columns.

`silver.int_order_context` has exactly one row per current order, containing its
customer version, status and purchase/lifecycle dates. Items, payments and reviews
each join to that unique lookup. They are never joined to one another.

Each item resolves product and seller history through a bounded interval lookup.
Uniqueness/interval tests and row-count, key-set and per-row measure comparisons
protect against fan-out. The order fact aggregates items and payments separately
before joining those one-row-per-order results.

Missing headers or dimension matches retain their facts. `has_order_context`
identifies missing headers on child facts; absent dimension keys remain NULL and
produce a dbt warning. There is no arbitrary nearest-version fallback.

## SCD policy

The versioning allowlist lives in `dbt/dbt_project.yml` under `vars.scd2_columns`.

| Dataset | Business key | Type 2 attributes | Type 1 attributes / behavior |
|---|---|---|---|
| customers | customer_id | customer_zip_code_prefix, customer_city, customer_state | customer_unique_id identity corrections |
| products | product_id | product_category_name | product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm |
| resellers | seller_id | seller_zip_code_prefix, seller_city, seller_state | No other non-key attributes in the supplied source |
| orders | order_id | None | Customer reference, status and all timestamps |
| order_items | order_id + order_item_id | None | Product/seller references, shipping limit, price, freight |
| order_payments | order_id + payment_sequential | None | Payment type, installments, value |
| order_reviews | review_id + order_id | None | Score, comment fields and timestamps |
| geolocation | All five columns | None | Current deduplicated lookup; a changed row is a delete/insert because no stable row identifier exists |

Keys define identity; a changed key is a delete/insert, not a Type 1 overwrite.
For facts, “Type 1” describes latest-state correction behavior rather than a
slowly changing dimension. The current facts contain no SCD validity columns.

Location history supports geography comparisons, and category history supports
product-mix analysis. Product measurements and descriptive metadata are treated
as corrections because this source lacks evidence of distinct physical product
versions. This is a documented portfolio assumption, not a universal business rule.
Any spelling correction in a tracked location field still opens a version.

Type 1 corrections update all existing versions of that business key. For example,
correcting a product's weight does not create a category version; both its old and
current category rows display the corrected weight. English category translations
are also current mappings from the seed and apply across history.

Bronze remains a full-row CDC audit trail regardless of the Type 1/2 policy.
Only changes to the tracked attributes open SCD2 versions. Deletes close active
versions, and reinsertions open new ones even when attributes are unchanged.
Multiple changes between dbt runs survive because versions derive from the event log.

SCD2 rows expose `version_id` (the boundary event ID), `valid_from`, exclusive
`valid_to`, `is_current` and boundary `batch_id`. `source_event_id`,
`last_observed_at` and `row_hash` describe the latest source record used for
Type 1 attributes; that hash is not a hash of a reconstructed historical row.

## Temporal attribution

All effective times are **pipeline observation times**. The static Olist extract
does not reveal what a dimension looked like on an original historical purchase date.

- Orders bind to the customer version when the order is first observed, reinserted,
  or its customer reference changes.
- All related facts reuse that same customer binding from the order context.
- Items bind to product/seller versions when first observed, reinserted, or either
  product/seller reference changes.
- Price, status, description or timestamp corrections do not advance these bindings.
- A product/seller reference correction intentionally re-resolves both item bindings.
- Dimension-only changes do not rewrite previously established fact attribution.

A dimension arriving after the required observation time remains unmatched unless
the source/reference or temporal policy is corrected. Inferring earlier validity
would invent history and is outside this implementation.

Type 1 dimension corrections intentionally restate descriptive history. Current
facts overwrite transactional corrections and disappear after source deletion.
Thus this model is not an “as of any previous report date” snapshot warehouse.

## Dates and aggregation

All detailed facts carry `order_date` from the purchase timestamp.
Payment source data has no payment timestamp; `order_date` is not a payment date.
Reviews additionally expose `review_date` and `review_answer_date`.
Orders expose approved, carrier, delivered and estimated delivery date roles.
Items expose `shipping_date` from the shipping-limit timestamp (a deadline,
not evidence of actual shipment).

`daily_sales` is an aggregate fact, connected only to calendar date. It cannot
support product, customer or seller slicers because those keys are absent.
Compare facts by aggregating each independently over shared dimensions. Do not sum
order totals with item totals, or join raw payment rows to item rows.

Product-level payment analysis would require a separate allocated fact with an
explicit business rule and rounding/reconciliation controls; it is not implemented.

## References

- [Kimball: Header/Line Fact Tables](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/header-line-fact-table/)
- [Kimball: Type 1 overwrite](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-1/)
- [Kimball: Multipass SQL](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multipass-sql/)
