import numpy as np
import pandas as pd
import pytest

from src.demand_forecasting import accuracy_metrics, forecast_weekly_demand


def test_accuracy_metrics() -> None:
    mae, mape = accuracy_metrics([100, 200], [90, 220])
    assert mae == 15
    assert mape == pytest.approx(10.0)


def test_forecast_has_holdout_metrics_and_12_future_weeks() -> None:
    index = np.arange(104)
    demand = 500 + 1.5 * index + 60 * np.sin(2 * np.pi * index / 52)
    history = pd.DataFrame(
        {
            "week_start": pd.date_range("2024-09-30", periods=104, freq="W-MON"),
            "demand_units": demand.round(),
        }
    )
    result = forecast_weekly_demand(history, periods=12, test_weeks=12)
    assert len(result.validation) == 12
    assert len(result.future) == 12
    assert result.future["forecast_demand"].ge(0).all()
    assert (result.future["lower_80"] <= result.future["forecast_demand"]).all()
    assert (result.future["forecast_demand"] <= result.future["upper_80"]).all()
    assert result.mae < 5
    assert result.mape < 2
    assert result.mae < result.baseline_mae


def test_forecast_rejects_short_history() -> None:
    history = pd.DataFrame(
        {
            "week_start": pd.date_range("2026-01-05", periods=20, freq="W-MON"),
            "demand_units": np.arange(20),
        }
    )
    with pytest.raises(ValueError, match="At least 64"):
        forecast_weekly_demand(history)
