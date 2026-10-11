from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CashFlowIntelligence:
    average_inflow: float
    average_outflow: float
    net_cash_flow: float
    runway_months: float
    liquidity_risk: str
    summary: str


@dataclass
class BudgetVariance:
    revenue_variance: float
    expense_variance: float
    profit_variance: float
    summary: str


@dataclass
class CostOptimizationResult:
    estimated_savings: float
    drivers: list[str]
    recommendation: str


@dataclass
class FinancialHealthScore:
    score: float
    breakdown: dict[str, float]
    status: str


@dataclass
class RiskExposureResult:
    operational_exposure: float
    revenue_exposure: float
    cost_exposure: float
    total_exposure: float
    summary: str


@dataclass
class LoanCreditIntelligence:
    emi_capacity: float
    estimated_credit_score: int
    default_risk: float
    optimal_loan_limit: float
    summary: str


def compute_cash_flow_intelligence(df: pd.DataFrame) -> CashFlowIntelligence:
    """Estimate liquidity posture and runway."""
    avg_inflow = float(df["revenue"].mean())
    avg_outflow = float(df["expenses"].mean())
    net_cash_flow = float(df["cash_flow"].mean())
    latest = df.iloc[-1]
    liquidity_buffer = max(float(latest["cash_flow"]) + float(latest["accounts_receivable"]) * 0.55, 1.0)
    monthly_burn = max(avg_outflow - avg_inflow, 0.0) + max(-net_cash_flow, 0.0)
    runway = round(liquidity_buffer / monthly_burn, 2) if monthly_burn > 0 else 18.0
    if runway < 3:
        risk = "HIGH"
    elif runway < 6:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return CashFlowIntelligence(
        average_inflow=round(avg_inflow, 2),
        average_outflow=round(avg_outflow, 2),
        net_cash_flow=round(net_cash_flow, 2),
        runway_months=runway,
        liquidity_risk=risk,
        summary=f"Runway is approximately {runway:.2f} months with {risk.lower()} liquidity risk.",
    )


def compute_budget_vs_actual(df: pd.DataFrame) -> BudgetVariance:
    """Approximate budget variance from trailing operational baseline."""
    latest = df.iloc[-1]
    trailing = df.iloc[:-1].tail(6) if len(df) > 1 else df
    budget_revenue = float(trailing["revenue"].median())
    budget_expenses = float(trailing["expenses"].median())
    budget_profit = float(trailing["profit"].median())
    rev_var = float(latest["revenue"] - budget_revenue)
    exp_var = float(latest["expenses"] - budget_expenses)
    profit_var = float(latest["profit"] - budget_profit)
    return BudgetVariance(
        revenue_variance=round(rev_var, 2),
        expense_variance=round(exp_var, 2),
        profit_variance=round(profit_var, 2),
        summary=(
            f"Revenue variance is {rev_var:,.0f}, expense variance is {exp_var:,.0f}, "
            f"and profit variance is {profit_var:,.0f} versus the rolling budget baseline."
        ),
    )


def compute_cost_optimization(df: pd.DataFrame) -> CostOptimizationResult:
    """Identify likely savings opportunities from expense pressure."""
    latest = df.iloc[-1]
    baseline_ratio = float(df["expense_ratio"].median())
    current_ratio = float(latest["expense_ratio"])
    overspend_ratio = max(current_ratio - baseline_ratio, 0.0)
    savings = round(float(latest["revenue"]) * overspend_ratio, 2)
    drivers: list[str] = []
    if current_ratio > baseline_ratio:
        drivers.append("Operating expense ratio is above baseline.")
    if float(latest["marketing_spend"]) > float(df["marketing_spend"].median()):
        drivers.append("Marketing spend is above the median run rate.")
    if float(latest["accounts_receivable"]) > float(df["accounts_receivable"].median()):
        drivers.append("Receivables are elevated, tying up liquidity.")
    recommendation = (
        "Trim discretionary spend, renegotiate variable costs, and improve receivables collection discipline."
        if savings > 0
        else "Current cost posture is close to baseline; focus on preserving efficiency."
    )
    return CostOptimizationResult(
        estimated_savings=savings,
        drivers=drivers or ["No major overspend drivers detected."],
        recommendation=recommendation,
    )


def compute_financial_health_score(df: pd.DataFrame, latest_risk_probability: float) -> FinancialHealthScore:
    """Compute a composite financial health score with explainable breakdown."""
    latest = df.iloc[-1]
    margin_component = max(min(float(latest["profit_margin"]) * 100, 30), -10) + 10
    liquidity_component = max(min(float(latest["cash_flow"]) / max(float(latest["revenue"]), 1.0) * 100, 25), -5) + 5
    stability_component = max(0.0, 25 - (float(df["revenue_growth"].std()) * 100))
    anomaly_component = max(0.0, 20 - (float(latest["anomaly_score"]) * 20))
    risk_component = max(0.0, 20 - (latest_risk_probability * 20))
    score = round(max(min(margin_component + liquidity_component + stability_component + anomaly_component + risk_component, 100), 0), 2)
    if score >= 80:
        status = "Strong"
    elif score >= 60:
        status = "Stable"
    elif score >= 40:
        status = "Watch"
    else:
        status = "Fragile"
    return FinancialHealthScore(
        score=score,
        breakdown={
            "margin": round(margin_component, 2),
            "liquidity": round(liquidity_component, 2),
            "stability": round(stability_component, 2),
            "anomaly_resilience": round(anomaly_component, 2),
            "risk_buffer": round(risk_component, 2),
        },
        status=status,
    )


def compute_risk_exposure(df: pd.DataFrame, latest_risk_probability: float, anomaly_score: float) -> RiskExposureResult:
    """Estimate monetary risk exposure by category."""
    latest = df.iloc[-1]
    revenue_exposure = round(float(latest["revenue"]) * latest_risk_probability, 2)
    cost_exposure = round(float(latest["expenses"]) * max(float(latest["expense_ratio"]) - float(df["expense_ratio"].median()), 0.0), 2)
    operational_exposure = round(float(latest["cash_flow"]) * max(anomaly_score, 0.1), 2)
    total = round(revenue_exposure + cost_exposure + abs(operational_exposure), 2)
    return RiskExposureResult(
        operational_exposure=abs(operational_exposure),
        revenue_exposure=revenue_exposure,
        cost_exposure=cost_exposure,
        total_exposure=total,
        summary=(
            f"Estimated exposure totals {total:,.0f}, led by revenue exposure of {revenue_exposure:,.0f} "
            f"and operational exposure of {abs(operational_exposure):,.0f}."
        ),
    )


def compute_loan_credit_intelligence(df: pd.DataFrame, latest_risk_probability: float) -> LoanCreditIntelligence:
    """Estimate credit strength, EMI capacity, and default risk."""
    avg_cash_flow = float(df["cash_flow"].mean())
    emi_capacity = round(max(avg_cash_flow * 0.32, 0.0), 2)
    negative_cash_flow_rate = float((df["cash_flow"] < 0).mean())
    default_risk = round(min(max((negative_cash_flow_rate * 0.55) + (latest_risk_probability * 0.45), 0.0), 1.0), 4)
    credit_score = int(max(min(820 - (default_risk * 420), 850), 300))
    optimal_loan_limit = round(emi_capacity * 24, 2)
    return LoanCreditIntelligence(
        emi_capacity=emi_capacity,
        estimated_credit_score=credit_score,
        default_risk=default_risk,
        optimal_loan_limit=optimal_loan_limit,
        summary=(
            f"Estimated credit score is {credit_score}, EMI capacity is {emi_capacity:,.0f}, "
            f"and default risk is {default_risk:.2f}."
        ),
    )
