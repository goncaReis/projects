import duckdb
import os

path = "olist-ecommerce.duckdb"

con = duckdb.connect(path)

tables = con.execute("SHOW TABLES").fetchall()

for table in tables:
    print(table)
