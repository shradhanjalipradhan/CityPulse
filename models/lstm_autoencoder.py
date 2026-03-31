"""
lstm_autoencoder.py — 6-channel LSTM Autoencoder for unsupervised anomaly detection.

Architecture:
  Input (batch, window=50, channels=6)
    → Encoder: LSTM(64) × 2 + Dropout(0.2) + Linear → latent(16)
    → Decoder: Linear → LSTM(64) × 2 + Linear → output(6)
  Anomaly score = mean reconstruction error (MSE) over all timesteps + channels
  Channel contributions = per-channel mean squared error
"""

import torch
import torch.nn as nn
from typing import Dict, Tuple

CHANNELS = ["temperature_c", "humidity_pct", "wind_speed_kmh",
            "precipitation_mm", "pm25", "pm10"]
N_CHANNELS = len(CHANNELS)
WINDOW_SIZE = 50
HIDDEN_SIZE = 64
LATENT_SIZE = 16
NUM_LAYERS = 2
DROPOUT = 0.2


class LSTMEncoder(nn.Module):
    """Encodes a multivariate time-series window into a fixed-size latent vector."""

    def __init__(self) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=N_CHANNELS,
            hidden_size=HIDDEN_SIZE,
            num_layers=NUM_LAYERS,
            dropout=DROPOUT,
            batch_first=True,
        )
        self.dropout = nn.Dropout(DROPOUT)
        self.fc = nn.Linear(HIDDEN_SIZE, LATENT_SIZE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, window, channels)
        Returns:
            latent: (batch, LATENT_SIZE)
        """
        _, (hidden, _) = self.lstm(x)
        # Take the last layer's hidden state
        last_hidden = hidden[-1]          # (batch, HIDDEN_SIZE)
        last_hidden = self.dropout(last_hidden)
        return self.fc(last_hidden)       # (batch, LATENT_SIZE)


class LSTMDecoder(nn.Module):
    """Decodes a latent vector back to a full time-series window."""

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        super().__init__()
        self.window_size = window_size
        self.fc_in = nn.Linear(LATENT_SIZE, HIDDEN_SIZE)
        self.lstm = nn.LSTM(
            input_size=HIDDEN_SIZE,
            hidden_size=HIDDEN_SIZE,
            num_layers=NUM_LAYERS,
            dropout=DROPOUT,
            batch_first=True,
        )
        self.fc_out = nn.Linear(HIDDEN_SIZE, N_CHANNELS)

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        """
        Args:
            latent: (batch, LATENT_SIZE)
        Returns:
            reconstruction: (batch, window, channels)
        """
        h = self.fc_in(latent)                              # (batch, HIDDEN_SIZE)
        # Repeat latent across time dimension to form decoder input sequence
        repeated = h.unsqueeze(1).repeat(1, self.window_size, 1)  # (batch, window, HIDDEN_SIZE)
        out, _ = self.lstm(repeated)                        # (batch, window, HIDDEN_SIZE)
        return self.fc_out(out)                             # (batch, window, channels)


class LSTMAutoencoder(nn.Module):
    """Full LSTM Autoencoder — encoder + decoder with anomaly scoring utilities."""

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        super().__init__()
        self.encoder = LSTMEncoder()
        self.decoder = LSTMDecoder(window_size=window_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, window, channels)
        Returns:
            reconstruction: (batch, window, channels)
        """
        latent = self.encoder(x)
        return self.decoder(latent)

    def reconstruction_error(
        self, x: torch.Tensor
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Computes per-sample anomaly score and per-channel contributions.

        Args:
            x: (batch, window, channels)

        Returns:
            scores: (batch,) — mean MSE per sample across all timesteps + channels
            contributions: dict mapping channel name → (batch,) mean MSE per channel
        """
        with torch.no_grad():
            recon = self.forward(x)
            # Per-timestep, per-channel squared error: (batch, window, channels)
            sq_err = (x - recon) ** 2
            # Per-sample score: mean over window and channels
            scores = sq_err.mean(dim=(1, 2))
            # Per-channel contribution: mean over window
            contributions = {
                ch: sq_err[:, :, i].mean(dim=1)
                for i, ch in enumerate(CHANNELS)
            }
        return scores, contributions
