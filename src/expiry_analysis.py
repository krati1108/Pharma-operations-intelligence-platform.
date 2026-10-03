"""Batch shelf-life monitoring and inventory value-at-risk analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATABASE_PATH, SIMULATION_DATE
from .database import query_dataframe


def classify_expiry_bucket(expiry_date: str | pd.Timestamp, as_of_date: str | pd.Timestamp) -> str:
    """Classify a batch into mutually exclusive shelf-life bands."""
    expiry = pd.Timestamp(expiry_date).normalize()
    as_of = pd.Timestamp(as_of_date).normalize()
    days = (expiry - as_of).days
    if days < 0:
        return "Expired"
    if days <= 90:
        return "0-90 days"
    if days <= 180:
        return "91-180 days"
    if days <= 365:
        return "181-365 days"
    return "Over 365 days"


def calculate_value_at_risk(
    batches: pd.DataFrame,
    horizon_days: int = 180,
    as_of_date: str | pd.Timestamp = SIMULATION_DATE,
) -> float:
    """Value on hand that is expired or will expire inside the selected horizon."""
    required = {"expiry_date", "inventory_quantity", "unit_cost"}
    missing = required.difference(batches.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if horizon_days < 0:
        raise ValueError("Horizon must be non-negative")
    days_to_expiry = (pd.to_datetime(batches["expiry_date"]) - pd.Timestamp(as_of_date)).dt.days
    exposure = batches.loc[days_to_expiry <= horizon_days]
    return float((exposure["inventory_quantity"] * exposure["unit_cost"]).sum())


def get_expiry_risk(
    database_path: Path | str = DATABASE_PATH,
    warehouse_id: str | None = None,
    include_long_dated: bool = True,
) -> pd.DataFrame:
    """Return batch-level expiry exposure ordered by urgency and value."""
    clauses: list[str] = []
    params: list[str] = []
    if warehouse_id:
        clauses.append("warehouse_id = ?")
        params.append(warehouse_id)
    if not include_long_dated:
        clauses.append("days_to_expiry <= 365")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return query_dataframe(
        f"SELECT * FROM v_expiry_risk {where} "
        "ORDER BY days_to_expiry ASC, inventory_value_at_risk DESC",
        tuple(params),
        database_path,
    )


def get_expiry_summary(database_path: Path | str = DATABASE_PATH) -> pd.DataFrame:
    """Aggregate expiry units and value by shelf-life band."""
    return query_dataframe(
        """
        SELECT
            expiry_bucket,
            COUNT(*) AS batch_count,
            SUM(inventory_quantity) AS inventory_units,
            ROUND(SUM(inventory_value_at_risk), 2) AS inventory_value_at_risk
        FROM v_expiry_risk
        GROUP BY expiry_bucket
        ORDER BY CASE expiry_bucket
            WHEN 'Expired' THEN 1
            WHEN '0-90 days' THEN 2
            WHEN '91-180 days' THEN 3
            WHEN '181-365 days' THEN 4
            ELSE 5 END
        """,
        database_path=database_path,
    )

