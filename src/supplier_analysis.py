"""Supplier reliability, quality, fill-rate, and lead-time analytics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATABASE_PATH
from .database import query_dataframe


def compute_supplier_metrics(purchase_orders: pd.DataFrame) -> dict[str, float]:
    """Calculate weighted delivery and quality KPIs for delivered orders."""
    required = {
        "status",
        "promised_delivery_date",
        "actual_delivery_date",
        "ordered_quantity",
        "received_quantity",
        "accepted_quantity",
    }
    missing = required.difference(purchase_orders.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    delivered = purchase_orders.loc[purchase_orders["status"] == "Delivered"].copy()
    if delivered.empty:
        return {
            "delivered_orders": 0,
            "on_time_delivery_pct": np.nan,
            "fill_rate_pct": np.nan,
            "acceptance_quality_pct": np.nan,
        }
    promised = pd.to_datetime(delivered["promised_delivery_date"])
    actual = pd.to_datetime(delivered["actual_delivery_date"])
    on_time = 100 * (actual <= promised).mean()
    ordered = delivered["ordered_quantity"].sum()
    received = delivered["received_quantity"].sum()
    accepted = delivered["accepted_quantity"].sum()
    return {
        "delivered_orders": len(delivered),
        "on_time_delivery_pct": float(on_time),
        "fill_rate_pct": float(100 * received / ordered) if ordered else np.nan,
        "acceptance_quality_pct": float(100 * accepted / received) if received else np.nan,
    }


def get_supplier_performance(database_path: Path | str = DATABASE_PATH) -> pd.DataFrame:
    """Return the supplier scorecard with a composite performance score."""
    frame = query_dataframe(
        "SELECT * FROM v_supplier_performance ORDER BY supplier_name",
        database_path=database_path,
    )
    metric_columns = ["on_time_delivery_pct", "acceptance_quality_pct", "fill_rate_pct"]
    frame["performance_score"] = (
        frame[metric_columns]
        .mul([0.45, 0.30, 0.25], axis=1)
        .sum(axis=1)
        .round(1)
    )
    frame["performance_tier"] = pd.cut(
        frame["performance_score"],
        bins=[-np.inf, 85, 92, np.inf],
        labels=["Needs Action", "Monitor", "Preferred"],
    ).astype(str)
    return frame.sort_values("performance_score", ascending=False)


def get_supplier_order_detail(
    supplier_id: str,
    database_path: Path | str = DATABASE_PATH,
) -> pd.DataFrame:
    """Return PO-level evidence behind a supplier score."""
    return query_dataframe(
        """
        SELECT
            po.purchase_order_id,
            p.product_name,
            w.warehouse_name,
            po.order_date,
            po.promised_delivery_date,
            po.actual_delivery_date,
            po.ordered_quantity,
            po.received_quantity,
            po.accepted_quantity,
            po.status,
            CASE WHEN po.status = 'Delivered'
                THEN CAST(julianday(po.actual_delivery_date) - julianday(po.promised_delivery_date)
                    AS INTEGER)
                END AS days_vs_promise
        FROM purchase_orders po
        JOIN products p ON p.product_id = po.product_id
        JOIN warehouses w ON w.warehouse_id = po.warehouse_id
        WHERE po.supplier_id = ?
        ORDER BY po.order_date DESC
        """,
        (supplier_id,),
        database_path,
    )

