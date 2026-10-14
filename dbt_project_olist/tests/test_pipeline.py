"""Integration tests use a disposable database, never the application's database."""
import csv
import os
from pathlib import Path
import subprocess
import uuid

import duckdb
import psycopg2
from psycopg2 import sql
import pytest

from pipeline.datasets import DATASETS
from pipeline.ingest import ingest, source_path
from pipeline.export import export_gold

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(monkeypatch):
    admin = psycopg2.connect('')
    admin.autocommit = True
    name = 'olist_test_' + uuid.uuid4().hex[:12]
    with admin.cursor() as cur:
        cur.execute(sql.SQL('create database {}').format(sql.Identifier(name)))
    monkeypatch.setenv('PGDATABASE', name)
    conn = psycopg2.connect('')
    try:
        yield conn
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(sql.SQL('drop database {} with (force)').format(sql.Identifier(name)))
        admin.close()


def scalar(conn, query):
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


def sample_rows():
    rows = {}
    for name, (columns, _) in DATASETS.items():
        row = {column: '1' for column in columns.split()}
        for column in row:
            if column.endswith('timestamp') or column.endswith('_date') or column == 'order_approved_at':
                row[column] = '2020-01-01 12:00:00'
        rows[name] = [row]
    rows['customers'][0]['customer_city'] = 'Original'
    rows['products'][0]['product_category_name'] = 'beleza_saude'
    rows['orders'][0]['order_status'] = 'delivered'
    rows['order_items'][0]['price'] = '12.34'
    rows['order_payments'][0]['payment_value'] = '13.34'
    return rows


def write_snapshot(directory, rows):
    directory.mkdir(exist_ok=True)
    for name, records in rows.items():
        with source_path(directory, name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, DATASETS[name][0].split())
            writer.writeheader()
            writer.writerows(records)


def build(conn, tmp_path, batch):
    env = os.environ.copy()
    subprocess.run(['dbt', 'build', '--project-dir', str(ROOT / 'dbt'),
                    '--profiles-dir', str(ROOT / 'dbt'), '--target-path', str(tmp_path / 'target'),
                    '--log-path', str(tmp_path / 'logs'),
                    '--vars', '{"batch_id":' + str(batch) + '}'], env=env, check=True)


def test_cdc_scd2_export_and_recovery(database, tmp_path):
    conn = database
    inputs = tmp_path / 'data'
    rows = sample_rows()
    # Exact duplicates collapse, including geolocation without a natural key.
    rows['geolocation'].append(rows['geolocation'][0].copy())
    write_snapshot(inputs, rows)
    first = ingest(conn, inputs)
    assert scalar(conn, 'select count(*) from bronze.cdc_events') == 8
    assert scalar(conn, 'select count(*) from bronze.current_rows') == 8
    build(conn, tmp_path, first)
    output = tmp_path / 'olist.duckdb'
    export_gold(conn, output, first)
    with duckdb.connect(str(output), read_only=True) as db:
        assert db.execute('select item_total from gold.fct_orders').fetchone()[0] == __import__('decimal').Decimal('12.34')
        assert db.execute('select count(*) from gold.dim_customers').fetchone()[0] == 1

    unchanged = ingest(conn, inputs)
    assert scalar(conn, 'select count(*) from bronze.cdc_events') == 8
    assert unchanged > first

    # Three changes before dbt runs: intermediate versions must survive.
    rows['customers'][0]['customer_city'] = 'Updated'
    write_snapshot(inputs, rows)
    ingest(conn, inputs)
    saved_customer = rows['customers'][0].copy()
    rows['customers'] = []
    rows['order_payments'] = []
    write_snapshot(inputs, rows)
    with pytest.raises(ValueError, match='empty snapshot'):
        ingest(conn, inputs)
    deleted = ingest(conn, inputs, allow_empty=True)
    build(conn, tmp_path, deleted)
    assert scalar(conn, 'select count(*) from silver.customers_current') == 0
    assert scalar(conn, 'select count(*) from silver.customers_history where valid_to is null') == 0
    export_gold(conn, output, deleted)
    with duckdb.connect(str(output), read_only=True) as db:
        assert db.execute('select count(*) from gold.fct_payments').fetchone()[0] == 0

    rows['customers'] = [saved_customer]
    rows['customers'][0]['customer_city'] = 'Returned'
    write_snapshot(inputs, rows)
    latest = ingest(conn, inputs, allow_empty=True)
    build(conn, tmp_path, latest)
    assert scalar(conn, 'select count(*) from silver.customers_history') == 3
    assert scalar(conn, 'select count(*) from silver.customers_current') == 1
    assert scalar(conn, "select customer_city from silver.customers_current") == 'Returned'
    assert scalar(conn, "select count(*) from bronze.cdc_events where dataset='customers'") == 4
    export_gold(conn, output, latest)
    with duckdb.connect(str(output), read_only=True) as db:
        assert db.execute('select batch_id from export_metadata').fetchone()[0] == latest
        assert db.execute('select count(*) from gold.dim_customers').fetchone()[0] == 3

    count_before = scalar(conn, 'select count(*) from bronze.batches')
    # Conflicting duplicates roll back the entire batch.
    duplicate = rows['customers'][0].copy()
    duplicate['customer_city'] = 'Conflicting'
    rows['customers'].append(duplicate)
    write_snapshot(inputs, rows)
    with pytest.raises(ValueError, match='Conflicting duplicate'):
        ingest(conn, inputs, allow_empty=True)
    assert scalar(conn, 'select count(*) from bronze.batches') == count_before

    source_path(inputs, 'orders').unlink()
    with pytest.raises(ValueError, match='requires all eight'):
        ingest(conn, inputs, allow_empty=True)
    assert scalar(conn, 'select count(*) from bronze.batches') == count_before

    # Export failure must leave the previously published file intact.
    with conn.cursor() as cur:
        cur.execute('create table gold.unsupported (value jsonb)')
    conn.commit()
    with pytest.raises(ValueError, match='Unsupported PostgreSQL type'):
        export_gold(conn, output, latest)
    with duckdb.connect(str(output), read_only=True) as db:
        assert db.execute('select batch_id from export_metadata').fetchone()[0] == latest

def test_selective_scd_and_enrichment(database, tmp_path):
    from decimal import Decimal
    conn = database
    inputs = tmp_path / 'data'
    rows = sample_rows()
    # Three items and two payments must never become six item rows.
    rows['order_items'] = [dict(rows['order_items'][0], order_item_id=str(i)) for i in (1, 2, 3)]
    rows['order_payments'] = [dict(rows['order_payments'][0], payment_sequential=str(i)) for i in (1, 2)]
    for dataset, key in [('customers','customer_id'),('products','product_id'),('resellers','seller_id')]:
        rows[dataset].append(dict(rows[dataset][0], **{key: '2'}))
    write_snapshot(inputs, rows)
    first = ingest(conn, inputs)
    build(conn, tmp_path, first)
    customer_key = scalar(conn, "select customer_version_id from gold.fct_orders where order_id='1'")
    product_key = scalar(conn, "select product_version_id from gold.fct_order_items where order_item_id=1")
    seller_key = scalar(conn, "select seller_version_id from gold.fct_order_items where order_item_id=1")
    assert scalar(conn, 'select count(*) from gold.fct_order_items') == 3
    assert scalar(conn, 'select count(*) from gold.fct_payments') == 2

    # Only Type 1 changes: no dimensional versions, no attribution drift.
    rows['customers'][0]['customer_unique_id'] = 'corrected-person'
    rows['products'][0]['product_weight_g'] = '999'
    rows['products'][0]['product_photos_qty'] = '5'
    rows['order_items'][0]['price'] = '20.00'
    rows['order_payments'][0]['payment_value'] = '21.00'
    rows['orders'][0]['order_status'] = 'shipped'
    rows['orders'][0]['order_purchase_timestamp'] = '2020-01-02 12:00:00'
    rows['order_reviews'][0]['review_comment_message'] = 'Corrected comment'
    write_snapshot(inputs, rows)
    batch = ingest(conn, inputs)
    build(conn, tmp_path, batch)
    assert scalar(conn, "select count(*) from silver.customers_history where customer_id='1'") == 1
    assert scalar(conn, "select count(*) from silver.products_history where product_id='1'") == 1
    assert scalar(conn, "select customer_unique_id from gold.dim_customers where customer_id='1'") == 'corrected-person'
    assert scalar(conn, "select product_weight_g from gold.dim_products where product_id='1'") == 999
    assert scalar(conn, 'select item_total from gold.fct_orders') == Decimal('44.68')

    # New SCD2 attributes, with a simultaneous Type 1 correction.
    rows['customers'][0]['customer_city'] = 'New city'
    rows['products'][0]['product_category_name'] = 'informatica_acessorios'
    rows['products'][0]['product_weight_g'] = '1000'
    rows['resellers'][0]['seller_state'] = 'SP'
    write_snapshot(inputs, rows)
    ingest(conn, inputs)
    # Another Type 1 update before dbt: applied to BOTH old and new versions.
    rows['products'][0]['product_weight_g'] = '1001'
    rows['customers'][0]['customer_unique_id'] = 'corrected-again'
    rows['order_items'][0]['price'] = '22.00'
    rows['orders'][0]['order_status'] = 'delivered'
    rows['order_items'].append(dict(rows['order_items'][0], order_item_id='4'))
    write_snapshot(inputs, rows)
    batch = ingest(conn, inputs)
    build(conn, tmp_path, batch)
    for name, key in [('customers','customer_id'),('products','product_id'),('resellers','seller_id')]:
        assert scalar(conn, f"select count(*) from silver.{name}_history where {key}='1'") == 2
    assert scalar(conn, "select count(*) from gold.dim_products where product_id='1' and product_weight_g=1001") == 2
    assert scalar(conn, "select count(*) from gold.dim_customers where customer_id='1' and customer_unique_id='corrected-again'") == 2
    assert scalar(conn, "select product_category_name from gold.dim_products where version_id=" + str(product_key)) == 'beleza_saude'
    assert scalar(conn, 'select customer_version_id from gold.fct_orders') == customer_key
    assert scalar(conn, 'select product_version_id from gold.fct_order_items where order_item_id=1') == product_key
    assert scalar(conn, 'select seller_version_id from gold.fct_order_items where order_item_id=1') == seller_key
    assert scalar(conn, 'select product_version_id from gold.fct_order_items where order_item_id=4') != product_key
    for fact in ['fct_order_items','fct_payments','fct_reviews']:
        assert scalar(conn, f'select bool_and(customer_version_id={customer_key}) from gold.{fact}')
        assert scalar(conn, f"select bool_and(order_date=date '2020-01-02' and order_status='delivered') from gold.{fact}")

    # Correcting an actual dimension reference intentionally changes attribution.
    rows['orders'][0]['customer_id'] = '2'
    rows['order_items'][0]['product_id'] = '2'
    rows['order_items'][0]['seller_id'] = '2'
    # Unmatched orders retain their facts, with NULL context and a visible warning.
    rows['order_items'].append(dict(rows['order_items'][1], order_id='missing'))
    rows['order_payments'].append(dict(rows['order_payments'][0], order_id='missing'))
    rows['order_reviews'].append(dict(rows['order_reviews'][0], order_id='missing'))
    write_snapshot(inputs, rows)
    batch = ingest(conn, inputs)
    build(conn, tmp_path, batch)
    customer2 = scalar(conn, "select version_id from gold.dim_customers where customer_id='2'")
    for fact in ['fct_orders','fct_order_items','fct_payments','fct_reviews']:
        assert scalar(conn, f"select bool_and(customer_version_id={customer2}) from gold.{fact} where order_id='1'")
    assert scalar(conn, 'select count(*) from gold.fct_order_items') == 5
    assert scalar(conn, 'select count(*) from gold.fct_payments') == 3
    for fact in ['fct_order_items','fct_payments','fct_reviews']:
        assert scalar(conn, f"select count(*) from gold.{fact} where order_id='missing' and not has_order_context and customer_version_id is null") == 1
    assert scalar(conn, "select p.product_id from gold.fct_order_items i join gold.dim_products p on i.product_version_id=p.version_id where i.order_id='1' and i.order_item_id=1") == '2'
    exported = tmp_path / 'enriched.duckdb'
    export_gold(conn, exported, batch)
    with duckdb.connect(str(exported), read_only=True) as db:
        assert db.execute('select count(*) from gold.fct_order_items').fetchone()[0] == 5
        assert db.execute("select customer_version_id from gold.fct_payments where order_id='1' limit 1").fetchone()[0] == customer2
        assert db.execute('select count(*) from gold.dim_payment_type').fetchone()[0] == 1

