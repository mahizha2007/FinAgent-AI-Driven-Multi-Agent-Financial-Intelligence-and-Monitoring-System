from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from models.autoencoder import AutoencoderModel
from models.isolation_forest import IsolationForestModel


@dataclass
class AnomalyAgentOutput:
    dataframe: pd.DataFrame
    hybrid_threshold: float


class AnomalyAgent:
    def __init__(
        self,
        isolation_model: IsolationForestModel,
        autoencoder_model: AutoencoderModel,
        hybrid_threshold: float = 0.68,
    ) -> None:
        self.isolation_model = isolation_model
        self.autoencoder_model = autoencoder_model
        self.hybrid_threshold = hybrid_threshold

    def run(self, base_df: pd.DataFrame, feature_matrix) -> AnomalyAgentOutput:
        iso_result = self.isolation_model.predict(feature_matrix)
        ae_result = self.autoencoder_model.predict(feature_matrix)

        hybrid_score = (iso_result.normalized_scores * 0.55) + (ae_result.normalized_scores * 0.45)
        hybrid_label = (hybrid_score >= self.hybrid_threshold).astype(int)

        output = base_df.copy()
        output["iforest_score"] = iso_result.normalized_scores
        output["autoencoder_score"] = ae_result.normalized_scores
        output["autoencoder_error"] = ae_result.reconstruction_error
        output["anomaly_score"] = hybrid_score.clip(0, 1)
        output["anomaly_label"] = hybrid_label
        return AnomalyAgentOutput(dataframe=output, hybrid_threshold=self.hybrid_threshold)
