# Power BI model

## Connect

Install the Windows 64-bit DuckDB ODBC driver. In Power BI Desktop choose
Get data → ODBC → DSN (None) → Advanced options. Use a connection string with
the full path to the published file and read-only access:

```text
Driver={DuckDB Driver};Database=C:\path\to\olist.duckdb;access_mode=read_only;
```

A WSL path such as `\\wsl.localhost\Ubuntu-24.04\home\<user>\projects\github_projects\dbt_project_olist\output\olist.duckdb`
can replace the example Windows path. Choose Default or Custom authentication
without credentials. Docker-created files may be root-owned and readable but not
writable by your Windows user; read-only mode avoids requesting write access.
Import the gold tables. `export_metadata` can support a last-refresh card.

## Relationships

Use dimension-to-fact, active, single-direction relationships with unique dimension
keys. Cardinality is normally one-to-many; a sample may happen to contain only one
fact per dimension member. Do not add relationships between facts.

| Dimension column | Fact columns |
|---|---|
| dim_customers.version_id | customer_version_id in fct_orders, fct_order_items, fct_payments, fct_reviews |
| dim_products.version_id | fct_order_items.product_version_id |
| dim_sellers.version_id | fct_order_items.seller_version_id |
| dim_order_status.order_status | order_status in all four detailed facts |
| dim_payment_type.payment_type | fct_payments.payment_type |
| dim_date.Date | order_date in all four detailed facts and daily_sales |

Keep historical dimension rows loaded; filtering to `is_current` would exclude
facts pointing to older versions. Business IDs can repeat across SCD2 versions.
Use `version_id` for relationships, hide technical keys/lineage columns from report
authors, and use dimension attributes for slicers.

Retain `order_id` on each fact as a degenerate dimension for identification and
drill-through. There is no shared order lookup in this export for cross-fact slicers.

Review-date and delivery-date analysis require explicit calendar roles:
use separate role-playing calendar tables for simultaneous date slicing, or
inactive relationships activated by `USERELATIONSHIP` in dedicated measures.
Do not mistake `valid_from` or `last_observed_at` for transaction dates.

The DAX calendar can continue to span purchase dates; extend its bounds to include
review/delivery dates before using those roles. Mark it as a date table.

## Measures and filter behavior

Create these as separate measures:

```dax
Item Sales = SUM ( fct_order_items[price] )
Freight = SUM ( fct_order_items[freight_value] )
Orders With Items = DISTINCTCOUNT ( fct_order_items[order_id] )
Item Sales per Order = DIVIDE ( [Item Sales], [Orders With Items] )
Orders = COUNTROWS ( fct_orders )
Payment Value = SUM ( fct_payments[payment_value] )
```

Product and seller slicers filter item measures, not order/payment/review facts.
Use `Orders With Items` for an order count under a product filter; `Orders` includes
orders without items and supports the dimensions directly connected to the order fact.

Avoid showing unallocated Payment Value by product: the amount would repeat
because product cannot filter that fact. Limit such visuals to shared dimensions,
or write an explicit measure guard returning BLANK for unsupported product/seller
contexts. Do not enable bidirectional relationships as a workaround.

Customer and purchase-date slicers can compare item sales and payments because
both facts now carry the same customer attribution and purchase date.
For review activity by review date, label that date role clearly.

The `daily_sales` table is optional for a detailed report. It responds only to its
calendar relationship. Its totals overlap detailed fact totals and must not be
added to them. Define cancellation, delivery and revenue-recognition rules before
presenting source item prices as business revenue.

## Refresh and upgrades

Refresh dimensions and facts together after rebuilding the pipeline. Selective
SCD2 collapses versions previously caused by Type 1 changes, so refresh existing
relationships and imported keys as a complete model upgrade.
A read-only ODBC connection may still hold a file handle; close readers if replacing
the publication fails. The previous file remains intact on export failure.

References: [Power BI star schema guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema),
[DuckDB ODBC setup](https://duckdb.org/docs/current/clients/odbc/windows).
