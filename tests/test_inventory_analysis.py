import math

import pandas as pd
import pytest

from src.inventory_analysis import (
    calculate_reorder_point,
    calculate_safety_stock,
    calculate_weeks_of_supply,
    classify_stockout_risk,
    recommend_order_quantity,
)


def test_calculate_safety_stock_uses_demand_variability() -> None:
    demand = pd.Series([90, 100, 110, 105, 95])
    result = calculate_safety_stock(demand, lead_time_weeks=4, service_level_z=1.65)
    expected = math.ceil(1.65 * demand.std(ddof=1) * math.sqrt(4))
    assert result == expected


def test_reorder_point_and_order_recommendation() -> None:
    reorder_point = calculate_reorder_point(100, lead_time_weeks=3, safety_stock=75)
    order_quantity = recommend_order_quantity(
        inventory_quantity=250,
        average_weekly_demand=100,
        lead_time_weeks=3,
        safety_stock=75,
        review_period_weeks=4,
    )
    assert reorder_point == 375
    assert order_quantity == 525


@pytest.mark.parametrize(
    ("inventory", "safety", "reorder", "weeks", "expected"),
    [
        (40, 50, 100, 2, "Critical"),
        (80, 50, 100, 3, "High"),
        (120, 50, 100, 5, "Watch"),
        (800, 50, 100, 8, "Healthy"),
    ],
)
def test_classify_stockout_risk(inventory, safety, reorder, weeks, expected) -> None:
    assert classify_stockout_risk(inventory, safety, reorder, weeks) == expected


def test_weeks_of_supply_handles_zero_demand() -> None:
    assert calculate_weeks_of_supply(200, 50) == 4
    assert math.isinf(calculate_weeks_of_supply(200, 0))


def test_inventory_functions_reject_negative_inputs() -> None:
    with pytest.raises(ValueError):
        calculate_weeks_of_supply(-1, 10)
    with pytest.raises(ValueError):
        recommend_order_quantity(-1, 10, 2, 5)

