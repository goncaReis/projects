# Snowflake ingestion

`load_to_snowflake.py` loads the eight Olist datasets from local CSV or
Parquet files into the Snowflake `RAW` schema. It replaces the previous
SnowSQL shell script.

## Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in the Snowflake values in `.env`. The executing role needs permission
to use the warehouse and create the configured database, schema, tables, and
temporary stages/file formats used by `write_pandas`.

Place source files in one of these directories:

```text
data/parquet/*.parquet  # preferred in auto mode
data/raw/*.csv          # fallback
```

## Run

Validate files and configuration without connecting:

```bash
python ingestion/load_to_snowflake.py --dry-run
```

Load all datasets, replacing existing RAW tables:

```bash
python ingestion/load_to_snowflake.py
```

Load CSV explicitly:

```bash
python ingestion/load_to_snowflake.py --format csv --data-dir data/raw
```

Load selected tables only:

```bash
python ingestion/load_to_snowflake.py --only RAW_ORDERS RAW_ORDER_ITEMS
```

Append rather than refresh:

```bash
python ingestion/load_to_snowflake.py --append
```

After ingestion, run the dbt project:

```bash
cd dbt_project
dbt build
```

## Table mapping

| Source file | Snowflake table |
|---|---|
| `olist_customers_dataset` | `RAW_CUSTOMERS` |
| `olist_geolocation_dataset` | `RAW_GEOLOCATION` |
| `olist_order_items_dataset` | `RAW_ORDER_ITEMS` |
| `olist_order_payments_dataset` | `RAW_ORDER_PAYMENTS` |
| `olist_order_reviews_dataset` | `RAW_ORDER_REVIEWS` |
| `olist_orders_dataset` | `RAW_ORDERS` |
| `olist_products_dataset` | `RAW_PRODUCTS` |
| `olist_sellers_dataset` | `RAW_RESELLERS` |
