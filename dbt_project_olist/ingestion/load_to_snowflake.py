"""Load the Olist CSV or Parquet datasets into Snowflake RAW tables.

The loader replaces the former SnowSQL-based ``ingestion.sh`` workflow. It:

1. Finds Olist files under ``data/parquet`` or ``data/raw``.
2. Reads them into pandas DataFrames.
3. Normalizes column names to uppercase Snowflake identifiers.
4. Creates or replaces the configured RAW tables with ``write_pandas``.
5. Verifies the resulting Snowflake row counts.

Credentials and target settings are read from environment variables. Copy
``.env.example`` to ``.env`` and fill in the required values before running.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector import SnowflakeConnection
from snowflake.connector.pandas_tools import write_pandas

LOGGER = logging.getLogger("olist_ingestion")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Dataset:
    """Mapping between an Olist source file and its Snowflake RAW table."""

    file_stem: str
    table_name: str


DATASETS: tuple[Dataset, ...] = (
    Dataset("olist_customers_dataset", "RAW_CUSTOMERS"),
    Dataset("olist_geolocation_dataset", "RAW_GEOLOCATION"),
    Dataset("olist_order_items_dataset", "RAW_ORDER_ITEMS"),
    Dataset("olist_order_payments_dataset", "RAW_ORDER_PAYMENTS"),
    Dataset("olist_order_reviews_dataset", "RAW_ORDER_REVIEWS"),
    Dataset("olist_orders_dataset", "RAW_ORDERS"),
    Dataset("olist_products_dataset", "RAW_PRODUCTS"),
    Dataset("olist_sellers_dataset", "RAW_RESELLERS"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load Olist CSV/Parquet files into Snowflake RAW tables."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing source files. When omitted, the loader checks "
            "data/parquet first and then data/raw."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("auto", "parquet", "csv"),
        default="auto",
        help="Input format. 'auto' prefers Parquet and falls back to CSV.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append rows instead of replacing each RAW table.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="TABLE",
        help="Load only selected RAW table names, for example RAW_ORDERS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and input files without connecting to Snowflake.",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def connection_parameters() -> dict[str, str]:
    params = {
        "account": required_env("SNOWFLAKE_ACCOUNT"),
        "user": required_env("SNOWFLAKE_USER"),
        "warehouse": required_env("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "OLIST_ECOMMERCE"),
        "schema": os.getenv("SNOWFLAKE_RAW_SCHEMA", "RAW"),
    }

    password = os.getenv("SNOWFLAKE_PASSWORD")
    authenticator = os.getenv("SNOWFLAKE_AUTHENTICATOR")
    role = os.getenv("SNOWFLAKE_ROLE")

    if password:
        params["password"] = password
    elif authenticator:
        params["authenticator"] = authenticator
    else:
        raise RuntimeError(
            "Set SNOWFLAKE_PASSWORD or SNOWFLAKE_AUTHENTICATOR "
            "(for example, externalbrowser)."
        )

    if role:
        params["role"] = role

    return params


def resolve_data_dir(requested: Path | None, file_format: str) -> Path:
    if requested is not None:
        directory = requested.expanduser().resolve()
        if not directory.is_dir():
            raise FileNotFoundError(f"Data directory does not exist: {directory}")
        return directory

    candidates: list[Path]
    if file_format == "csv":
        candidates = [PROJECT_ROOT / "data" / "raw"]
    elif file_format == "parquet":
        candidates = [PROJECT_ROOT / "data" / "parquet"]
    else:
        candidates = [
            PROJECT_ROOT / "data" / "parquet",
            PROJECT_ROOT / "data" / "raw",
        ]

    for directory in candidates:
        if directory.is_dir() and any(directory.iterdir()):
            return directory

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"No populated data directory found. Checked: {searched}")


def locate_source_file(data_dir: Path, dataset: Dataset, file_format: str) -> Path:
    extensions = (
        (".parquet", ".csv") if file_format == "auto" else (f".{file_format}",)
    )
    for extension in extensions:
        candidate = data_dir / f"{dataset.file_stem}{extension}"
        if candidate.is_file():
            return candidate
    expected = ", ".join(f"{dataset.file_stem}{ext}" for ext in extensions)
    raise FileNotFoundError(f"Missing source file in {data_dir}: expected {expected}")


def read_source(path: Path) -> pd.DataFrame:
    LOGGER.info("Reading %s", path)
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    if frame.empty:
        raise ValueError(f"Source file contains no rows: {path}")

    frame.columns = [str(column).strip().upper() for column in frame.columns]
    duplicate_columns = frame.columns[frame.columns.duplicated()].tolist()
    if duplicate_columns:
        raise ValueError(f"Duplicate columns after normalization: {duplicate_columns}")

    # Snowflake handles Python None/NaN as SQL NULL through write_pandas.
    return frame


def ensure_target_namespace(connection: SnowflakeConnection, database: str, schema: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE IF NOT EXISTS "{database}"')
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{database}"."{schema}"')
        cursor.execute(f'USE DATABASE "{database}"')
        cursor.execute(f'USE SCHEMA "{schema}"')


def load_frame(
    connection: SnowflakeConnection,
    frame: pd.DataFrame,
    table_name: str,
    database: str,
    schema: str,
    append: bool,
) -> int:
    if not append:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{database}"."{schema}"."{table_name}"')

    success, chunk_count, rows_written, _ = write_pandas(
        conn=connection,
        df=frame,
        table_name=table_name,
        database=database,
        schema=schema,
        auto_create_table=True,
        overwrite=False,
        quote_identifiers=True,
    )

    if not success:
        raise RuntimeError(f"write_pandas reported failure for {table_name}")

    LOGGER.info(
        "Loaded %s rows into %s.%s.%s in %s chunk(s)",
        rows_written,
        database,
        schema,
        table_name,
        chunk_count,
    )
    return int(rows_written)


def snowflake_row_count(
    connection: SnowflakeConnection, database: str, schema: str, table_name: str
) -> int:
    query = f'SELECT COUNT(*) FROM "{database}"."{schema}"."{table_name}"'
    with connection.cursor() as cursor:
        cursor.execute(query)
        result = cursor.fetchone()
    if result is None:
        raise RuntimeError(f"Could not retrieve row count for {table_name}")
    return int(result[0])


def selected_datasets(only: Iterable[str] | None) -> tuple[Dataset, ...]:
    if not only:
        return DATASETS

    requested = {name.upper() for name in only}
    known = {dataset.table_name for dataset in DATASETS}
    unknown = requested - known
    if unknown:
        raise ValueError(
            f"Unknown table(s): {', '.join(sorted(unknown))}. "
            f"Valid values: {', '.join(sorted(known))}"
        )
    return tuple(dataset for dataset in DATASETS if dataset.table_name in requested)


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        datasets = selected_datasets(args.only)
        data_dir = resolve_data_dir(args.data_dir, args.format)
        sources = {
            dataset: locate_source_file(data_dir, dataset, args.format)
            for dataset in datasets
        }
        LOGGER.info("Using input directory: %s", data_dir)

        if args.dry_run:
            for dataset, source in sources.items():
                LOGGER.info("Validated %s -> %s", source.name, dataset.table_name)
            LOGGER.info("Dry run completed successfully; no Snowflake changes were made.")
            return 0

        params = connection_parameters()
        database = params["database"].upper()
        schema = params["schema"].upper()

        LOGGER.info("Connecting to Snowflake account %s", params["account"])
        with snowflake.connector.connect(**params) as connection:
            ensure_target_namespace(connection, database, schema)

            for dataset, source in sources.items():
                frame = read_source(source)
                source_rows = len(frame)
                rows_written = load_frame(
                    connection,
                    frame,
                    dataset.table_name,
                    database,
                    schema,
                    args.append,
                )
                target_rows = snowflake_row_count(
                    connection, database, schema, dataset.table_name
                )

                if rows_written != source_rows:
                    raise RuntimeError(
                        f"Load validation failed for {dataset.table_name}: "
                        f"source={source_rows}, written={rows_written}"
                    )
                if not args.append and target_rows != source_rows:
                    raise RuntimeError(
                        f"Row-count validation failed for {dataset.table_name}: "
                        f"source={source_rows}, Snowflake={target_rows}"
                    )

                LOGGER.info(
                    "Validated %s: source=%s, Snowflake=%s",
                    dataset.table_name,
                    source_rows,
                    target_rows,
                )

        LOGGER.info("Olist ingestion completed successfully.")
        return 0

    except Exception as exc:  # noqa: BLE001 - CLI boundary logs a clean error.
        LOGGER.error("Ingestion failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
