from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BayesianRiskResult:
    risk_probability: float
    uncertainty: float
    components: dict[str, float]


def compute_bayesian_risk(
    anomaly_score: float,
    forecast_risk: float,
    historical_anomaly_frequency: float,
) -> BayesianRiskResult:
    """Compute a lightweight Bayesian-style posterior risk estimate."""
    prior_risk = min(max(historical_anomaly_frequency, 0.01), 0.99)
    likelihood = min(max((anomaly_score * 0.55) + (forecast_risk * 0.45), 0.01), 0.99)
    evidence = (likelihood * prior_risk) + ((1 - likelihood) * (1 - prior_risk))
    posterior = (likelihood * prior_risk) / max(evidence, 1e-9)
    uncertainty = round(abs(0.5 - posterior) * 2, 4)
    return BayesianRiskResult(
        risk_probability=round(min(max(posterior, 0.0), 1.0), 4),
        uncertainty=round(1 - uncertainty, 4),
        components={
            "prior_risk": round(prior_risk, 4),
            "likelihood": round(likelihood, 4),
            "forecast_risk": round(forecast_risk, 4),
            "historical_anomaly_frequency": round(historical_anomaly_frequency, 4),
        },
    )
