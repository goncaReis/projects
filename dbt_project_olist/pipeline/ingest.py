"""Atomically compare complete CSV snapshots and persist immutable CDC events."""
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path

import psycopg2

from pipeline.datasets import DATASETS

DDL = """
create schema if not exists bronze;
create table if not exists bronze.batches (
    batch_id bigint generated always as identity primary key,
    observed_at timestamptz not null unique,
    source_dir text not null
);
create table if not exists bronze.current_rows (
    dataset text not null, business_key text not null, payload jsonb not null,
    row_hash text not null, batch_id bigint not null references bronze.batches,
    primary key (dataset, business_key)
);
create table if not exists bronze.cdc_events (
    event_id bigint generated always as identity primary key,
    batch_id bigint not null references bronze.batches,
    dataset text not null, business_key text not null,
    operation char(1) not null check (operation in ('I','U','D')),
    payload jsonb not null, row_hash text not null,
    unique (batch_id, dataset, business_key)
);
create index if not exists cdc_history on bronze.cdc_events(dataset, business_key, batch_id);
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def source_path(directory, dataset):
    path = directory / f'olist_{dataset}_dataset.csv'
    if dataset == 'resellers':
        alternate = directory / 'olist_sellers_dataset.csv'
        if path.exists() and alternate.exists():
            raise ValueError('Provide only one sellers/resellers file, not both.')
        if alternate.exists():
            return alternate
    return path


def stage_file(cursor, path, dataset, allow_empty):
    columns, keys = DATASETS[dataset]
    columns = columns.split()
    keys = keys.split() or columns
    count = 0
    with path.open(encoding='utf-8-sig', newline='') as source, tempfile.TemporaryFile(mode='w+', encoding='utf-8', newline='') as staged:
        reader = csv.DictReader(source)
        if reader.fieldnames != columns:
            raise ValueError(f'{path.name}: unexpected columns; expected {columns}')
        writer = csv.writer(staged)
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'{path.name}: malformed row near line {reader.line_num}')
            row = {name: value if value != '' else None for name, value in row.items()}
            if any(row[key] is None for key in keys):
                raise ValueError(f'{path.name}: null key near line {reader.line_num}')
            payload = canonical(row)
            writer.writerow([dataset, canonical([row[key] for key in keys]), payload,
                             hashlib.sha256(payload.encode()).hexdigest()])
            count += 1
        if count == 0 and not allow_empty:
            raise ValueError(f'{path.name}: empty snapshot refused; use --allow-empty for intentional deletion')
        staged.seek(0)
        cursor.copy_expert('copy incoming_raw from stdin with (format csv)', staged)
    print(f'{dataset}: read {count:,} rows', flush=True)


def ingest(connection, directory, allow_empty=False):
    directory = Path(directory).resolve()
    paths = {name: source_path(directory, name) for name in DATASETS}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError(f'Full snapshot requires all eight files. Missing: {missing}')
    with connection:
        with connection.cursor() as cur:
            cur.execute('select pg_advisory_xact_lock(78234591)')
            cur.execute(DDL)
            cur.execute('create temporary table incoming_raw (dataset text, business_key text, payload jsonb, row_hash text) on commit drop')
            for name, path in paths.items():
                stage_file(cur, path, name, allow_empty)
            cur.execute("""select dataset, business_key from incoming_raw
                group by dataset, business_key having count(distinct row_hash)>1 limit 1""")
            conflict = cur.fetchone()
            if conflict:
                raise ValueError(f'Conflicting duplicate business key: {conflict}')
            cur.execute('create temporary table incoming on commit drop as select distinct * from incoming_raw')
            cur.execute('create unique index on incoming(dataset, business_key)')
            cur.execute('analyze incoming')
            cur.execute("""insert into bronze.batches(observed_at, source_dir)
                select greatest(clock_timestamp(), coalesce(max(observed_at) + interval '1 microsecond', clock_timestamp())), %s
                from bronze.batches returning batch_id""", (str(directory),))
            batch_id = cur.fetchone()[0]
            cur.execute("""insert into bronze.cdc_events(batch_id,dataset,business_key,operation,payload,row_hash)
                select %s,i.dataset,i.business_key,case when c.business_key is null then 'I' else 'U' end,i.payload,i.row_hash
                from incoming i left join bronze.current_rows c using(dataset,business_key)
                where c.business_key is null or i.row_hash<>c.row_hash
                union all
                select %s,c.dataset,c.business_key,'D',c.payload,c.row_hash
                from bronze.current_rows c left join incoming i using(dataset,business_key)
                where i.business_key is null""", (batch_id, batch_id))
            cur.execute("""delete from bronze.current_rows c where not exists
                (select 1 from incoming i where i.dataset=c.dataset and i.business_key=c.business_key)""")
            cur.execute("""insert into bronze.current_rows select dataset,business_key,payload,row_hash,%s from incoming
                on conflict (dataset,business_key) do update set payload=excluded.payload,
                row_hash=excluded.row_hash,batch_id=excluded.batch_id
                where bronze.current_rows.row_hash<>excluded.row_hash""", (batch_id,))
            cur.execute('select operation,count(*) from bronze.cdc_events where batch_id=%s group by operation', (batch_id,))
            counts = dict(cur.fetchall())
    print(f'Committed batch {batch_id}: {counts or "no changes"}', flush=True)
    return batch_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--allow-empty', action='store_true')
    args = parser.parse_args()
    connection = psycopg2.connect('')
    try:
        ingest(connection, args.data_dir, args.allow_empty)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
