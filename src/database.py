"""SQLite connection, schema creation, loading, and query helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from .config import DATABASE_PATH, SCHEMA_PATH, SIMULATION_DATE


@contextmanager
def connect(database_path: Path | str = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection configured for relational integrity."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_schema(
    database_path: Path | str = DATABASE_PATH,
    schema_path: Path | str = SCHEMA_PATH,
    as_of_date: str | pd.Timestamp = SIMULATION_DATE,
) -> None:
    """Create a fresh analytics schema from the version-controlled SQL file."""
    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with connect(database_path) as connection:
        connection.executescript(schema_file.read_text(encoding="utf-8"))
        normalized_date = pd.Timestamp(as_of_date).normalize().strftime("%Y-%m-%d")
        connection.execute(
            "UPDATE simulation_config SET as_of_date = ? WHERE config_id = 1",
            (normalized_date,),
        )


def load_frames(
    frames: Mapping[str, pd.DataFrame],
    database_path: Path | str = DATABASE_PATH,
) -> None:
    """Load normalized frames in dependency order within one transaction."""
    load_order = [
        "suppliers",
        "products",
        "warehouses",
        "weekly_sales",
        "inventory_batches",
        "purchase_orders",
    ]
    missing = [table for table in load_order if table not in frames]
    if missing:
        raise ValueError(f"Missing required data frames: {', '.join(missing)}")

    with connect(database_path) as connection:
        for table in reversed(load_order):
            connection.execute(f"DELETE FROM {table}")
        for table in load_order:
            frames[table].to_sql(table, connection, if_exists="append", index=False)


def query_dataframe(
    query: str,
    params: tuple | dict | None = None,
    database_path: Path | str = DATABASE_PATH,
) -> pd.DataFrame:
    """Return a SQL query as a pandas DataFrame."""
    if not Path(database_path).exists():
        raise FileNotFoundError(
            f"Database not found at {database_path}. Run `python -m src.data_pipeline`."
        )
    with connect(database_path) as connection:
        return pd.read_sql_query(query, connection, params=params)


def table_counts(database_path: Path | str = DATABASE_PATH) -> dict[str, int]:
    """Return row counts for every core table."""
    tables = (
        "products",
        "warehouses",
        "suppliers",
        "weekly_sales",
        "inventory_batches",
        "purchase_orders",
    )
    with connect(database_path) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
