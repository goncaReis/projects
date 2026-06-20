#!/bin/bash

set -e # stop on error

DB="OLIST_ECOMMERCE"
SCHEMA="RAW"
STAGE="OLIST_STAGE"
CONN="my_conn"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
SQL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting Olist ingestion into Snowflake..."

# -----------------------------
# 1. Create schema
# -----------------------------
snowsql -c $CONN -q "
CREATE OR REPLACE SCHEMA $DB.$SCHEMA;
"

# -----------------------------
# 2. Create stage (safe to rerun)
# -----------------------------
snowsql -c $CONN -q "
CREATE OR REPLACE STAGE $DB.$SCHEMA.$STAGE;
"

# -----------------------------
# 3. Upload ALL CSV files
# -----------------------------
echo "Uploading CSV files to stage..."

snowsql -c $CONN -q "
PUT file://$DATA_DIR/*.csv @$DB.$SCHEMA.$STAGE AUTO_COMPRESS=TRUE;
"

# -----------------------------
# 4. File format (safe to rerun)
# -----------------------------
snowsql -c $CONN -q "
CREATE OR REPLACE FILE FORMAT $DB.$SCHEMA.CSV_FORMAT
TYPE = CSV
SKIP_HEADER = 1
FIELD_OPTIONALLY_ENCLOSED_BY = '\"'
NULL_IF = ('NULL', 'null', '');
"

# -----------------------------
# 5. CREATE TABLES FROM SQL FILES
# -----------------------------
echo "Creating tables..."

for file in "$SQL_DIR"/*.sql; do
  echo "Running $file"

  snowsql -c $CONN -f "$file"
done

# -----------------------------
# 6. Load tables
# ----------------------------
echo "Loading tables into RAW schema..."

load_table() {
  TABLE=$1
  FILE_PATTERN=$2

  echo "Loading $TABLE"

  snowsql -c $CONN -q "

  COPY INTO $DB.$SCHEMA.$TABLE
  FROM @$DB.$SCHEMA.$STAGE
  FILE_FORMAT = (FORMAT_NAME = $DB.$SCHEMA.CSV_FORMAT)
  PATTERN = '.*$FILE_PATTERN.*'
  ON_ERROR = 'ABORT_STATEMENT';
  "
}

# -----------------------------
# 7. Run ingestion per table
# -----------------------------
load_table "raw_customers" "olist_customers_dataset"
load_table "raw_order_items" "olist_order_items_dataset"
load_table "raw_order_reviews" "olist_order_reviews_dataset"
load_table "raw_products" "olist_products_dataset"
load_table "raw_geolocation" "olist_geolocation_dataset"
load_table "raw_order_payments" "olist_order_payments_dataset"
load_table "raw_orders" "olist_orders_dataset"
load_table "raw_resellers" "olist_sellers_dataset"

echo "Ingestion complete!"
