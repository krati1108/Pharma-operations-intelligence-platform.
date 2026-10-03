"""Reusable seasonal-trend demand forecasting with holdout validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from .config import DATABASE_PATH
from .database import query_dataframe


@dataclass(frozen=True)
class ForecastResult:
    """Forecast output suitable for validation tables and dashboard plots."""

    history: pd.DataFrame
    validation: pd.DataFrame
    future: pd.DataFrame
    mae: float
    mape: float
    baseline_mae: float
    baseline_mape: float


def _time_features(indices: np.ndarray) -> np.ndarray:
    """Represent trend plus annual, semiannual, and quarterly seasonality."""
    t = indices.astype(float)
    return np.column_stack(
        [
            t,
            np.sin(2 * np.pi * t / 52),
            np.cos(2 * np.pi * t / 52),
            np.sin(4 * np.pi * t / 52),
            np.cos(4 * np.pi * t / 52),
            np.sin(8 * np.pi * t / 52),
            np.cos(8 * np.pi * t / 52),
        ]
    )


def accuracy_metrics(actual: pd.Series | np.ndarray, predicted: pd.Series | np.ndarray) -> tuple[float, float]:
    """Return MAE and zero-safe MAPE percentages."""
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.shape != predicted_array.shape or actual_array.size == 0:
        raise ValueError("Actual and predicted arrays must be non-empty and the same shape")
    mae = float(np.mean(np.abs(actual_array - predicted_array)))
    nonzero = actual_array != 0
    mape = (
        float(np.mean(np.abs((actual_array[nonzero] - predicted_array[nonzero]) / actual_array[nonzero])) * 100)
        if nonzero.any()
        else float("nan")
    )
    return mae, mape


def forecast_weekly_demand(
    series: pd.DataFrame,
    periods: int = 12,
    test_weeks: int = 12,
    alpha: float = 1.0,
) -> ForecastResult:
    """Fit, validate, refit, and forecast an aggregated weekly demand series.

    A regularized regression captures the long-run trend and multiple Fourier
    seasonal components. The final 12 observed weeks are held out before the
    model is refit to all history for the forward forecast.
    """
    required = {"week_start", "demand_units"}
    missing = required.difference(series.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if periods <= 0 or test_weeks <= 0:
        raise ValueError("Forecast and test horizons must be positive")

    weekly = series.copy()
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    weekly = (
        weekly.groupby("week_start", as_index=False)["demand_units"]
        .sum()
        .sort_values("week_start")
    )
    minimum_history = test_weeks + 52
    if len(weekly) < minimum_history:
        raise ValueError(
            f"At least {minimum_history} weekly observations are required for annual validation"
        )

    y = weekly["demand_units"].to_numpy(dtype=float)
    indices = np.arange(len(weekly))
    split = len(weekly) - test_weeks
    validation_model = Ridge(alpha=alpha)
    validation_model.fit(_time_features(indices[:split]), y[:split])
    validation_pred = np.clip(
        validation_model.predict(_time_features(indices[split:])),
        0,
        None,
    )
    mae, mape = accuracy_metrics(y[split:], validation_pred)
    seasonal_naive_pred = y[indices[split:] - 52]
    baseline_mae, baseline_mape = accuracy_metrics(y[split:], seasonal_naive_pred)
    residuals = y[split:] - validation_pred
    residual_lower, residual_upper = np.quantile(residuals, [0.10, 0.90])
    residual_lower = min(float(residual_lower), 0.0)
    residual_upper = max(float(residual_upper), 0.0)

    final_model = Ridge(alpha=alpha)
    final_model.fit(_time_features(indices), y)
    future_indices = np.arange(len(weekly), len(weekly) + periods)
    future_pred = np.clip(final_model.predict(_time_features(future_indices)), 0, None)
    next_week = weekly["week_start"].max() + pd.Timedelta(weeks=1)
    future_dates = pd.date_range(next_week, periods=periods, freq="W-MON")

    history = weekly.rename(columns={"demand_units": "actual_demand"})
    validation = pd.DataFrame(
        {
            "week_start": weekly["week_start"].iloc[split:].to_numpy(),
            "actual_demand": y[split:],
            "predicted_demand": validation_pred,
            "seasonal_naive_demand": seasonal_naive_pred,
        }
    )
    future = pd.DataFrame(
        {
            "week_start": future_dates,
            "forecast_demand": future_pred.round(1),
            "lower_80": np.clip(future_pred + residual_lower, 0, None).round(1),
            "upper_80": np.clip(future_pred + residual_upper, 0, None).round(1),
        }
    )
    return ForecastResult(
        history,
        validation,
        future,
        mae,
        mape,
        baseline_mae,
        baseline_mape,
    )


def get_demand_history(
    database_path: Path | str = DATABASE_PATH,
    product_id: str | None = None,
    warehouse_id: str | None = None,
) -> pd.DataFrame:
    """Fetch weekly demand at network, product, warehouse, or position grain."""
    clauses: list[str] = []
    params: list[str] = []
    if product_id:
        clauses.append("product_id = ?")
        params.append(product_id)
    if warehouse_id:
        clauses.append("warehouse_id = ?")
        params.append(warehouse_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return query_dataframe(
        f"""
        SELECT week_start, SUM(demand_units) AS demand_units
        FROM weekly_sales
        {where}
        GROUP BY week_start
        ORDER BY week_start
        """,
        tuple(params),
        database_path,
    )
