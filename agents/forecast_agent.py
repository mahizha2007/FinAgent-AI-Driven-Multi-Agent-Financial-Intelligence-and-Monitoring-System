from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from prophet import Prophet


@dataclass
class ForecastAgentOutput:
    revenue_forecast: pd.DataFrame
    expense_forecast: pd.DataFrame


class ForecastAgent:
    def _fallback_forecast(self, df: pd.DataFrame, column: str, periods: int) -> pd.DataFrame:
        """Return a simple carry-forward forecast when Prophet cannot be used safely."""
        history = df[["date", column]].copy().dropna()
        if history.empty:
            history = pd.DataFrame({"date": [pd.Timestamp.today().normalize()], column: [0.0]})
        last_date = history["date"].max()
        last_value = float(history[column].iloc[-1])
        future_dates = pd.date_range(start=last_date, periods=periods + 1, freq="MS")
        values = np.repeat(last_value, len(future_dates))
        return pd.DataFrame(
            {
                "ds": future_dates,
                "yhat": values,
                "yhat_lower": values * 0.95,
                "yhat_upper": values * 1.05,
                "metric": column,
            }
        )

    def _fit_forecast(self, df: pd.DataFrame, column: str, periods: int) -> pd.DataFrame:
        prophet_df = df[["date", column]].rename(columns={"date": "ds", column: "y"}).dropna()
        if len(prophet_df) < 2 or prophet_df["y"].notna().sum() < 2:
            return self._fallback_forecast(df, column, periods)
        try:
            model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
            model.fit(prophet_df)
            forecast = model.predict(model.make_future_dataframe(periods=periods, freq="MS"))
            return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].assign(metric=column)
        except Exception:
            return self._fallback_forecast(df, column, periods)

    def run(self, df: pd.DataFrame, periods: int = 6) -> ForecastAgentOutput:
        return ForecastAgentOutput(
            revenue_forecast=self._fit_forecast(df, "revenue", periods),
            expense_forecast=self._fit_forecast(df, "expenses", periods),
        )
