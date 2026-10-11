from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class StressTestResult:
    baseline_profit: float
    stressed_profit: float
    profit_impact: float
    risk_score: float
    applied_revenue_drop: float
    applied_expense_increase: float


BUILTIN_STRESS_SCENARIOS = [
    {"name": "Mild Revenue Dip", "revenue_drop_pct": 0.05, "expense_increase_pct": 0.00},
    {"name": "Seasonal Revenue Dip", "revenue_drop_pct": 0.10, "expense_increase_pct": 0.00},
    {"name": "Marketing Overrun", "revenue_drop_pct": 0.00, "expense_increase_pct": 0.08},
    {"name": "Cost Inflation", "revenue_drop_pct": 0.00, "expense_increase_pct": 0.12},
    {"name": "Demand Shock", "revenue_drop_pct": 0.15, "expense_increase_pct": 0.05},
    {"name": "Supply Chain Stress", "revenue_drop_pct": 0.08, "expense_increase_pct": 0.15},
    {"name": "Pricing Pressure", "revenue_drop_pct": 0.12, "expense_increase_pct": 0.03},
    {"name": "Working Capital Squeeze", "revenue_drop_pct": 0.06, "expense_increase_pct": 0.10},
    {"name": "Operating Inefficiency", "revenue_drop_pct": 0.04, "expense_increase_pct": 0.18},
    {"name": "Competitive Hit", "revenue_drop_pct": 0.18, "expense_increase_pct": 0.04},
    {"name": "Severe Downturn", "revenue_drop_pct": 0.25, "expense_increase_pct": 0.12},
    {"name": "Extreme Liquidity Stress", "revenue_drop_pct": 0.30, "expense_increase_pct": 0.18},
]


def run_stress_test(
    latest_record: pd.Series,
    revenue_drop_pct: float = 0.0,
    expense_increase_pct: float = 0.0,
) -> StressTestResult:
    baseline_profit = float(latest_record["profit"])
    stressed_revenue = float(latest_record["revenue"]) * (1 - revenue_drop_pct)
    stressed_expenses = float(latest_record["expenses"]) * (1 + expense_increase_pct)
    stressed_profit = stressed_revenue - stressed_expenses
    profit_impact = stressed_profit - baseline_profit

    revenue_pressure = min(revenue_drop_pct / 0.4, 1.0)
    expense_pressure = min(expense_increase_pct / 0.4, 1.0)
    downside_pressure = min(abs(profit_impact) / max(abs(baseline_profit), 1.0), 1.0)
    risk_score = round((revenue_pressure * 0.4) + (expense_pressure * 0.3) + (downside_pressure * 0.3), 4)

    return StressTestResult(
        baseline_profit=round(baseline_profit, 2),
        stressed_profit=round(stressed_profit, 2),
        profit_impact=round(profit_impact, 2),
        risk_score=risk_score,
        applied_revenue_drop=revenue_drop_pct,
        applied_expense_increase=expense_increase_pct,
    )


def get_builtin_stress_scenarios() -> list[dict[str, float | str]]:
    """Return built-in financial stress scenarios."""
    return BUILTIN_STRESS_SCENARIOS


def generate_custom_scenarios(
    max_revenue_drop_pct: float,
    max_expense_increase_pct: float,
    count: int = 5,
) -> list[dict[str, float | str]]:
    """Generate a small scenario set between mild and severe custom bounds."""
    scenarios: list[dict[str, float | str]] = []
    count = max(1, count)
    for index in range(1, count + 1):
        factor = index / count
        scenarios.append(
            {
                "name": f"Custom Scenario {index}",
                "revenue_drop_pct": round(max_revenue_drop_pct * factor, 4),
                "expense_increase_pct": round(max_expense_increase_pct * factor, 4),
            }
        )
    return scenarios


def parse_scenario_text(text: str) -> tuple[float, float]:
    lower = text.lower()
    revenue_drop_pct = 0.0
    expense_increase_pct = 0.0

    revenue_match = re.search(r"revenue\s+(?:drops?|decreases?)\s+(\d+(?:\.\d+)?)\s*%", lower)
    expense_match = re.search(r"expenses?\s+(?:increase|increases|rise|rises|grow|grows)\s+(\d+(?:\.\d+)?)\s*%", lower)

    if revenue_match:
        revenue_drop_pct = float(revenue_match.group(1)) / 100.0
    if expense_match:
        expense_increase_pct = float(expense_match.group(1)) / 100.0

    return revenue_drop_pct, expense_increase_pct
