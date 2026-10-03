"""Shared paths and simulation constants."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DATABASE_PATH = DATA_DIR / "pharma_operations.db"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

# The demo has a fixed business date so screenshots, tests, and KPI values are stable.
SIMULATION_DATE = "2026-09-27"
RANDOM_SEED = 42

