from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class RiskAgentOutput:
    dataframe: pd.DataFrame
    latest_risk_level: str


class RiskAgent:
    def run(self, df: pd.DataFrame, baseline_df: pd.DataFrame | None = None) -> RiskAgentOutput:
        result = df.copy()
        benchmark = baseline_df if baseline_df is not None else result
        revenue_growth_median = float(benchmark["revenue_growth"].median())
        margin_median = float(benchmark["profit_margin"].median())

        risk_scores = []
        risk_levels = []
        for _, row in result.iterrows():
            anomaly_component = float(row["anomaly_score"]) * 0.55
            growth_penalty = 0.2 if float(row["revenue_growth"]) < revenue_growth_median else 0.05
            margin_penalty = 0.2 if float(row["profit_margin"]) < margin_median else 0.05
            expense_penalty = min(float(row["expense_ratio"]), 1.0) * 0.15
            score = round(min(anomaly_component + growth_penalty + margin_penalty + expense_penalty, 1.0), 4)
            risk_scores.append(score)
            if score >= 0.75:
                risk_levels.append("HIGH")
            elif score >= 0.45:
                risk_levels.append("MEDIUM")
            else:
                risk_levels.append("LOW")

        result["risk_score"] = risk_scores
        result["risk_level"] = risk_levels
        return RiskAgentOutput(dataframe=result, latest_risk_level=risk_levels[-1])
