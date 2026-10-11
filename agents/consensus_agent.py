from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConsensusResult:
    final_score: float
    consensus_confidence: float
    weighted_components: dict[str, float]


class ConsensusAgent:
    """Aggregate weighted scores from multiple intelligence agents."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or {
            "anomaly_score": 0.35,
            "risk_probability": 0.30,
            "forecast_risk": 0.15,
            "stress_risk": 0.10,
            "historical_anomaly_frequency": 0.10,
        }

    def run(self, scores: dict[str, float]) -> ConsensusResult:
        weighted_components = {
            name: round(scores.get(name, 0.0) * weight, 4)
            for name, weight in self.weights.items()
        }
        final_score = round(sum(weighted_components.values()), 4)
        total_weight = sum(self.weights.values()) or 1.0
        dispersion = sum(abs((scores.get(name, 0.0) * self.weights[name]) - final_score / total_weight) for name in self.weights)
        consensus_confidence = round(max(0.0, min(1.0, 1 - dispersion)), 4)
        return ConsensusResult(
            final_score=min(max(final_score, 0.0), 1.0),
            consensus_confidence=consensus_confidence,
            weighted_components=weighted_components,
        )
