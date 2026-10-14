"""Run snapshot ingestion, tested dbt models, then atomic DuckDB publication."""
import argparse
import json
from pathlib import Path
import subprocess

import psycopg2

from pipeline.ingest import ingest
from pipeline.export import export_gold

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, default=ROOT / 'output' / 'olist.duckdb')
    parser.add_argument('--allow-empty', action='store_true')
    args = parser.parse_args()
    conn = psycopg2.connect('')
    try:
        # Same lock as standalone ingestion; held across commits and dbt subprocesses.
        with conn.cursor() as cur:
            cur.execute('select pg_advisory_lock(78234591)')
        batch_id = ingest(conn, args.data_dir, args.allow_empty)
        subprocess.run(['dbt', 'build', '--project-dir', str(ROOT / 'dbt'),
                        '--profiles-dir', str(ROOT / 'dbt'),
                        '--vars', json.dumps({'batch_id': batch_id})], check=True)
        export_gold(conn, args.output, batch_id)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
