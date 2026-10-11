from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CounterfactualResult:
    expected_profit: float
    actual_profit: float
    financial_impact: float
    summary: str


def compute_counterfactual_impact(current_row: pd.Series, baseline_df: pd.DataFrame) -> CounterfactualResult:
    """Estimate financial impact by comparing actual profit to expected baseline profit."""
    comparable = baseline_df.tail(min(6, len(baseline_df)))
    expected_profit = float(comparable["profit"].median()) if not comparable.empty else float(current_row["profit"])
    actual_profit = float(current_row["profit"])
    financial_impact = round(actual_profit - expected_profit, 2)
    direction = "loss" if financial_impact < 0 else "gain"
    summary = (
        f"Expected profit was {expected_profit:,.0f}, actual profit was {actual_profit:,.0f}, "
        f"creating a {direction} of {abs(financial_impact):,.0f}."
    )
    return CounterfactualResult(
        expected_profit=round(expected_profit, 2),
        actual_profit=round(actual_profit, 2),
        financial_impact=financial_impact,
        summary=summary,
    )
