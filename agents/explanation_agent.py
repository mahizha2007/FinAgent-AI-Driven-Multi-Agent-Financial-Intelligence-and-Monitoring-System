from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import shap
except Exception:  # pragma: no cover - optional dependency fallback
    shap = None


@dataclass
class ExplanationAgentOutput:
    explanation_text: str
    top_features: list[tuple[str, float]]


class ExplanationAgent:
    def __init__(self, score_function, background_data: np.ndarray, feature_names: list[str]) -> None:
        self.background = background_data[: min(10, len(background_data))]
        self.score_function = score_function
        self.feature_names = feature_names
        self.explainer = None

    def quick_explanation(self, row_features: np.ndarray) -> ExplanationAgentOutput:
        """Produce a fast heuristic explanation without SHAP."""
        row = np.array(row_features).reshape(-1)
        values = np.abs(row)
        top_features = sorted(zip(self.feature_names, values), key=lambda item: item[1], reverse=True)[:3]
        explanation = "Primary anomaly drivers: " + ", ".join(
            f"{name} ({value:.3f})" for name, value in top_features
        ) + "."
        return ExplanationAgentOutput(explanation_text=explanation, top_features=top_features)

    def run(self, row_features: np.ndarray) -> ExplanationAgentOutput:
        if shap is None:
            return self.quick_explanation(row_features)
        if self.explainer is None:
            self.explainer = shap.KernelExplainer(self.score_function, self.background)
        shap_values = self.explainer.shap_values(row_features, nsamples=20)
        values = np.abs(np.array(shap_values).reshape(-1))
        top_features = sorted(zip(self.feature_names, values), key=lambda item: item[1], reverse=True)[:3]
        explanation = "Primary anomaly drivers: " + ", ".join(
            f"{name} ({value:.3f})" for name, value in top_features
        ) + "."
        return ExplanationAgentOutput(explanation_text=explanation, top_features=top_features)
