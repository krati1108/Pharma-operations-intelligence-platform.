import pandas as pd
import pytest

from src.expiry_analysis import calculate_value_at_risk, classify_expiry_bucket


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        ("2026-09-26", "Expired"),
        ("2026-12-26", "0-90 days"),
        ("2027-03-26", "91-180 days"),
        ("2027-08-01", "181-365 days"),
        ("2028-01-01", "Over 365 days"),
    ],
)
def test_classify_expiry_bucket_boundaries(expiry, expected) -> None:
    assert classify_expiry_bucket(expiry, "2026-09-27") == expected


def test_value_at_risk_includes_expired_and_near_expiry_batches() -> None:
    batches = pd.DataFrame(
        {
            "expiry_date": ["2026-09-20", "2026-11-01", "2027-10-01"],
            "inventory_quantity": [10, 20, 100],
            "unit_cost": [5.0, 7.5, 20.0],
        }
    )
    assert calculate_value_at_risk(batches, 90, "2026-09-27") == 200.0

