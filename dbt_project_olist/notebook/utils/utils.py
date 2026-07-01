from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data/parquet"

def load_data():

    tables = {
            "orders": pd.read_parquet(DATA_DIR / "olist_orders_dataset.parquet"),
            "customers": pd.read_parquet(DATA_DIR / "olist_customers_dataset.parquet"),
            "geolocation": pd.read_parquet(DATA_DIR / "olist_geolocation_dataset.parquet"),
            "order_items": pd.read_parquet(DATA_DIR / "olist_order_items_dataset.parquet"),
            "reviews": pd.read_parquet(DATA_DIR / "olist_order_reviews_dataset.parquet"),
            "payments": pd.read_parquet(DATA_DIR / "olist_order_payments_dataset.parquet"),
            "resellers": pd.read_parquet(DATA_DIR / "olist_resellers_dataset.parquet"),
            "products": pd.read_parquet(DATA_DIR / "olist_products_dataset.parquet")
    }

    print("The data was sucessfully loaded")

    return tables

def pa():
    print(DATA_DIR)


