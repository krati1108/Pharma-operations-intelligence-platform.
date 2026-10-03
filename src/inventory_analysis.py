"""Inventory health, safety-stock, and replenishment calculations."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATABASE_PATH
from .database import query_dataframe


def calculate_safety_stock(
    weekly_demand: pd.Series,
    lead_time_weeks: float,
    service_level_z: float = 1.65,
) -> int:
    """Estimate safety stock using demand variability during lead time.

    The default z-score approximates a 95% cycle-service target. At least two
    observations and a positive lead time are required.
    """
    demand = pd.to_numeric(weekly_demand, errors="coerce").dropna()
    if len(demand) < 2:
        raise ValueError("At least two demand observations are required")
    if lead_time_weeks <= 0:
        raise ValueError("Lead time must be positive")
    if service_level_z < 0:
        raise ValueError("Service-level z-score cannot be negative")
    return int(np.ceil(service_level_z * demand.std(ddof=1) * np.sqrt(lead_time_weeks)))


def calculate_reorder_point(
    average_weekly_demand: float,
    lead_time_weeks: float,
    safety_stock: int,
) -> int:
    """Return lead-time demand plus safety stock, rounded up to whole units."""
    if min(average_weekly_demand, lead_time_weeks, safety_stock) < 0:
        raise ValueError("Demand, lead time, and safety stock must be non-negative")
    return int(np.ceil(average_weekly_demand * lead_time_weeks + safety_stock))


def calculate_weeks_of_supply(inventory_quantity: float, average_weekly_demand: float) -> float:
    """Return inventory coverage; infinite coverage represents zero demand."""
    if inventory_quantity < 0 or average_weekly_demand < 0:
        raise ValueError("Inventory and demand must be non-negative")
    if average_weekly_demand == 0:
        return float("inf")
    return float(inventory_quantity / average_weekly_demand)


def recommend_order_quantity(
    inventory_quantity: float,
    average_weekly_demand: float,
    lead_time_weeks: float,
    safety_stock: float,
    review_period_weeks: float = 4,
) -> int:
    """Order up to lead-time plus review-period demand and safety stock."""
    values = (
        inventory_quantity,
        average_weekly_demand,
        lead_time_weeks,
        safety_stock,
        review_period_weeks,
    )
    if min(values) < 0:
        raise ValueError("Replenishment inputs must be non-negative")
    target = average_weekly_demand * (lead_time_weeks + review_period_weeks) + safety_stock
    return max(0, int(np.ceil(target - inventory_quantity)))


def classify_stockout_risk(
    inventory_quantity: float,
    safety_stock: float,
    reorder_point: float,
    weeks_of_supply: float,
) -> str:
    """Assign the same action-oriented risk tier used by the SQL view."""
    if inventory_quantity <= safety_stock:
        return "Critical"
    if inventory_quantity <= reorder_point:
        return "High"
    if weeks_of_supply < 6:
        return "Watch"
    return "Healthy"


def get_inventory_health(
    database_path: Path | str = DATABASE_PATH,
    warehouse_id: str | None = None,
    therapeutic_area: str | None = None,
) -> pd.DataFrame:
    """Read inventory positions with optional warehouse and therapy filters."""
    clauses: list[str] = []
    params: list[str] = []
    if warehouse_id:
        clauses.append("warehouse_id = ?")
        params.append(warehouse_id)
    if therapeutic_area:
        clauses.append("therapeutic_area = ?")
        params.append(therapeutic_area)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return query_dataframe(
        f"SELECT * FROM v_inventory_health {where} "
        "ORDER BY replenishment_flag DESC, weeks_of_supply ASC",
        tuple(params),
        database_path,
    )


def get_replenishment_recommendations(
    database_path: Path | str = DATABASE_PATH,
    warehouse_id: str | None = None,
) -> pd.DataFrame:
    """Return actionable orders, including estimated purchase value."""
    inventory = get_inventory_health(database_path, warehouse_id=warehouse_id)
    recommendations = inventory.loc[inventory["recommended_order_quantity"] > 0].copy()
    recommendations["estimated_order_value"] = (
        recommendations["recommended_order_quantity"] * recommendations["unit_cost"]
    ).round(2)
    return recommendations.sort_values(
        ["stockout_risk", "weeks_of_supply"],
        key=lambda col: col.map({"Critical": 0, "High": 1, "Watch": 2, "Healthy": 3})
        if col.name == "stockout_risk"
        else col,
    )


def get_warehouse_summary(database_path: Path | str = DATABASE_PATH) -> pd.DataFrame:
    """Aggregate inventory value, risk, and coverage by warehouse."""
    return query_dataframe(
        """
        SELECT
            warehouse_id,
            warehouse_name,
            region,
            ROUND(SUM(inventory_value), 2) AS inventory_value,
            SUM(inventory_quantity) AS inventory_units,
            SUM(CASE WHEN stockout_risk = 'Critical' THEN 1 ELSE 0 END) AS critical_skus,
            SUM(replenishment_flag) AS replenishment_flags,
            ROUND(SUM(inventory_quantity) / NULLIF(SUM(avg_weekly_demand), 0), 2)
                AS weeks_of_supply
        FROM v_inventory_health
        GROUP BY warehouse_id, warehouse_name, region
        ORDER BY inventory_value DESC
        """,
        database_path=database_path,
    )

