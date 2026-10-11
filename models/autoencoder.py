from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


class FinancialAutoencoder(nn.Module):
    def __init__(self, input_dim: int) -> None:
        super().__init__()
        hidden_dim = max(4, input_dim * 2)
        bottleneck_dim = max(2, input_dim // 2)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, bottleneck_dim),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(bottleneck_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(inputs)
        return self.decoder(latent)


@dataclass
class AutoencoderResult:
    reconstruction_error: np.ndarray
    normalized_scores: np.ndarray
    labels: np.ndarray


class AutoencoderModel:
    def __init__(
        self,
        input_dim: int,
        epochs: int = 150,
        batch_size: int = 8,
        learning_rate: float = 0.001,
        threshold_quantile: float = 0.88,
        seed: int = 42,
    ) -> None:
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.network = FinancialAutoencoder(input_dim=input_dim).to(self.device)
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.threshold_quantile = threshold_quantile
        self.threshold_: float | None = None
        self.train_error_min_: float | None = None
        self.train_error_max_: float | None = None

    def fit(self, features: np.ndarray) -> None:
        tensor_data = torch.tensor(features, dtype=torch.float32)
        dataset = TensorDataset(tensor_data)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        optimizer = torch.optim.Adam(self.network.parameters(), lr=self.learning_rate)
        criterion = nn.MSELoss()

        self.network.train()
        for _ in range(self.epochs):
            for (batch,) in loader:
                batch = batch.to(self.device)
                optimizer.zero_grad(set_to_none=True)
                reconstructed = self.network(batch)
                loss = criterion(reconstructed, batch)
                loss.backward()
                optimizer.step()

        errors = self._compute_reconstruction_error(features)
        self.threshold_ = float(np.quantile(errors, self.threshold_quantile))
        self.train_error_min_ = float(np.min(errors))
        self.train_error_max_ = float(np.max(errors))

    def _compute_reconstruction_error(self, features: np.ndarray) -> np.ndarray:
        self.network.eval()
        with torch.no_grad():
            tensor_data = torch.tensor(features, dtype=torch.float32).to(self.device)
            reconstructed = self.network(tensor_data)
            error = torch.mean((reconstructed - tensor_data) ** 2, dim=1)
        return error.cpu().numpy()

    def predict(self, features: np.ndarray) -> AutoencoderResult:
        if self.threshold_ is None:
            raise RuntimeError("AutoencoderModel must be fitted before prediction.")

        errors = self._compute_reconstruction_error(features)
        min_error = self.train_error_min_ if self.train_error_min_ is not None else float(np.min(errors))
        max_error = self.train_error_max_ if self.train_error_max_ is not None else float(np.max(errors))
        denominator = max(max_error - min_error, 1e-9)
        normalized = np.clip((errors - min_error) / denominator, 0, 1)
        labels = np.where(errors >= self.threshold_, 1, 0)
        return AutoencoderResult(
            reconstruction_error=errors,
            normalized_scores=normalized,
            labels=labels,
        )
