from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecisionEngineResult:
    decision: str
    confidence_score: float
    reasoning_trace: str
    recommended_action: str
    severity: str


class DecisionIntelligenceEngine:
    """Centralized financial decision engine."""

    def evaluate(
        self,
        anomaly_score: float,
        risk_probability: float,
        forecast_risk: float,
        stress_risk: float,
        historical_anomaly_frequency: float,
        financial_impact: float,
        consensus_confidence: float,
    ) -> DecisionEngineResult:
        final_risk = (
            anomaly_score * 0.25
            + risk_probability * 0.30
            + forecast_risk * 0.15
            + stress_risk * 0.15
            + historical_anomaly_frequency * 0.15
        )
        confidence = round(min(max((final_risk * 0.7) + (consensus_confidence * 0.3), 0.0), 1.0), 4)

        if final_risk >= 0.72 or financial_impact <= -20000:
            decision = "ALERT"
            recommended_action = "Escalate immediately, review root cause, and notify stakeholders."
            severity = "CRITICAL"
        elif final_risk >= 0.45:
            decision = "INVESTIGATE"
            recommended_action = "Investigate the anomaly path, validate forecast assumptions, and monitor next refresh."
            severity = "WARNING"
        else:
            decision = "IGNORE"
            recommended_action = "Keep under observation and revisit if trend deterioration continues."
            severity = "INFO"

        reasoning_trace = "\n".join(
            [
                f"Anomaly score contributed {anomaly_score:.2f}.",
                f"Bayesian risk probability was {risk_probability:.2f}.",
                f"Forecast risk was {forecast_risk:.2f} and stress risk was {stress_risk:.2f}.",
                f"Historical anomaly frequency was {historical_anomaly_frequency:.2f}.",
                f"Counterfactual financial impact was {financial_impact:,.0f}.",
                f"Consensus confidence was {consensus_confidence:.2f}.",
            ]
        )
        return DecisionEngineResult(
            decision=decision,
            confidence_score=confidence,
            reasoning_trace=reasoning_trace,
            recommended_action=recommended_action,
            severity=severity,
        )
