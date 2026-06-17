from pathlib import Path
import duckdb
import os

DB_FILE = "olist-ecommerce.duckdb"
CSV_PATH = Path("olist-ecommerce")

con = duckdb.connect(DB_FILE)

for file in os.listdir(CSV_PATH):
    last_char = file.rfind('_dataset')
    table_name = file[0:last_char]
    con.execute(f"""
        CREATE TABLE '{table_name}' AS
        SELECT *
        FROM read_csv_auto('{CSV_PATH / file}')
        """
        )

