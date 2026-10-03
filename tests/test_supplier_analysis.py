import pandas as pd

from src.supplier_analysis import compute_supplier_metrics


def test_compute_supplier_metrics_is_quantity_weighted() -> None:
    orders = pd.DataFrame(
        {
            "status": ["Delivered", "Delivered", "Open"],
            "promised_delivery_date": ["2026-01-10", "2026-01-10", "2026-02-01"],
            "actual_delivery_date": ["2026-01-09", "2026-01-12", None],
            "ordered_quantity": [100, 300, 500],
            "received_quantity": [100, 270, 0],
            "accepted_quantity": [98, 250, 0],
        }
    )
    result = compute_supplier_metrics(orders)
    assert result["delivered_orders"] == 2
    assert result["on_time_delivery_pct"] == 50.0
    assert result["fill_rate_pct"] == 92.5
    assert round(result["acceptance_quality_pct"], 2) == 94.05


def test_compute_supplier_metrics_handles_no_deliveries() -> None:
    orders = pd.DataFrame(
        {
            "status": ["Open"],
            "promised_delivery_date": ["2026-01-10"],
            "actual_delivery_date": [None],
            "ordered_quantity": [100],
            "received_quantity": [0],
            "accepted_quantity": [0],
        }
    )
    assert compute_supplier_metrics(orders)["delivered_orders"] == 0

