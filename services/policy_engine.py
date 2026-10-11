from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyEvaluationResult:
    adjusted_decision: str
    policy_flags: list[str]
    requires_approval: bool
    rationale: str


class PolicyEngine:
    """Hybrid policy engine that complements ML decisions with control rules."""

    def evaluate(
        self,
        ml_decision: str,
        risk_probability: float,
        financial_health_score: float,
        liquidity_risk: str,
        total_exposure: float,
        budget_profit_variance: float,
    ) -> PolicyEvaluationResult:
        flags: list[str] = []
        decision = ml_decision
        if risk_probability >= 0.75:
            flags.append("High posterior risk.")
        if financial_health_score < 45:
            flags.append("Financial health below policy threshold.")
        if liquidity_risk == "HIGH":
            flags.append("Liquidity runway is below comfort level.")
        if total_exposure >= 50000:
            flags.append("Monetary exposure exceeds escalation threshold.")
        if budget_profit_variance < -15000:
            flags.append("Profit variance is materially below budget.")

        if flags and decision == "IGNORE":
            decision = "INVESTIGATE"
        if len(flags) >= 3 and decision != "ALERT":
            decision = "ALERT"

        requires_approval = decision == "ALERT" or total_exposure >= 80000
        rationale = " | ".join(flags) if flags else "No policy escalations triggered."
        return PolicyEvaluationResult(
            adjusted_decision=decision,
            policy_flags=flags,
            requires_approval=requires_approval,
            rationale=rationale,
        )
