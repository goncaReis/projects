"""Publish the tested gold schema to a new DuckDB file and atomically replace output."""
import os
from pathlib import Path
import tempfile

import duckdb
import pyarrow as pa
from psycopg2 import sql

# Explicit types preserve decimals, timestamps and empty tables without CSV inference.
def column_type(column):
    oid = column.type_code
    if oid in (20, 21, 23):
        return 'BIGINT', pa.int64()
    if oid == 16:
        return 'BOOLEAN', pa.bool_()
    if oid in (700, 701):
        return 'DOUBLE', pa.float64()
    if oid == 1700:
        precision, scale = column.precision or 38, column.scale or 0
        if precision > 38:
            raise ValueError(f'Numeric precision exceeds DuckDB capacity: {column.name}')
        return f'DECIMAL({precision},{scale})', pa.decimal128(precision, scale)
    if oid == 1082:
        return 'DATE', pa.date32()
    if oid in (1114, 1184):
        return ('TIMESTAMPTZ', pa.timestamp('us', tz='UTC')) if oid == 1184 else ('TIMESTAMP', pa.timestamp('us'))
    if oid in (25, 1042, 1043):
        return 'VARCHAR', pa.string()
    raise ValueError(f'Unsupported PostgreSQL type {oid} for {column.name}')


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


def export_gold(conn, destination, batch_id):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.olist-', suffix='.duckdb', dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    temporary.unlink()  # DuckDB creates its own valid file.
    try:
        with duckdb.connect(str(temporary)) as output:
            output.execute('create schema gold')
            with conn.cursor() as cur:
                cur.execute("""select table_name from information_schema.tables
                    where table_schema='gold' and table_type='BASE TABLE' order by table_name""")
                tables = [row[0] for row in cur.fetchall()]
            if not tables:
                raise ValueError('No gold tables found; run dbt build first.')
            for table in tables:
                with conn.cursor(name='gold_export') as cur:
                    cur.execute(sql.SQL('select * from gold.{}').format(sql.Identifier(table)))
                    rows = cur.fetchmany(10000)
                    columns = list(cur.description)
                    types = [column_type(column) for column in columns]
                    definition = ','.join(quoted(col.name) + ' ' + kind[0] for col, kind in zip(columns, types))
                    output.execute(f'create table gold.{quoted(table)} ({definition})')
                    count = 0
                    while rows:
                        batch = pa.Table.from_arrays(
                            [pa.array([row[index] for row in rows], type=kind[1]) for index, kind in enumerate(types)],
                            names=[column.name for column in columns])
                        output.register('incoming_batch', batch)
                        output.execute(f'insert into gold.{quoted(table)} select * from incoming_batch')
                        output.unregister('incoming_batch')
                        count += len(rows)
                        rows = cur.fetchmany(10000)
                actual = output.execute(f'select count(*) from gold.{quoted(table)}').fetchone()[0]
                if actual != count:
                    raise RuntimeError(f'Export count mismatch for {table}')
                print(f'DuckDB gold.{table}: {count:,} rows', flush=True)
            output.execute('create table export_metadata as select ?::bigint as batch_id, current_timestamp as exported_at', [batch_id])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Published {destination}', flush=True)
