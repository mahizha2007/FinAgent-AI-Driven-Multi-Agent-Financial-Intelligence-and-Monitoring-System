from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest


@dataclass
class IsolationForestResult:
    raw_scores: np.ndarray
    normalized_scores: np.ndarray
    labels: np.ndarray


class IsolationForestModel:
    def __init__(
        self,
        contamination: float = 0.12,
        random_state: int = 42,
        n_estimators: int = 200,
    ) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=n_estimators,
        )
        self.is_fitted = False
        self.train_score_min_: float | None = None
        self.train_score_max_: float | None = None

    def fit(self, features: np.ndarray) -> None:
        self.model.fit(features)
        train_signal = -self.model.score_samples(features)
        self.train_score_min_ = float(np.min(train_signal))
        self.train_score_max_ = float(np.max(train_signal))
        self.is_fitted = True

    def predict(self, features: np.ndarray) -> IsolationForestResult:
        if not self.is_fitted:
            raise RuntimeError("IsolationForestModel must be fitted before prediction.")

        anomaly_signal = -self.model.score_samples(features)
        min_score = self.train_score_min_ if self.train_score_min_ is not None else float(np.min(anomaly_signal))
        max_score = self.train_score_max_ if self.train_score_max_ is not None else float(np.max(anomaly_signal))
        denominator = max(max_score - min_score, 1e-9)
        normalized = np.clip((anomaly_signal - min_score) / denominator, 0, 1)
        labels = np.where(self.model.predict(features) == -1, 1, 0)
        return IsolationForestResult(
            raw_scores=anomaly_signal,
            normalized_scores=normalized,
            labels=labels,
        )
