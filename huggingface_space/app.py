"""
app.py — FastAPI inference server for CityPulse Switzerland.
Runs inside a Docker container on HuggingFace Spaces (CPU Basic, free tier).

Endpoints:
  POST /predict   — run inference for one city
  GET  /health    — liveness check
  GET  /cities    — list supported cities
  GET  /models    — show loaded model metadata
"""

import logging
import os
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Constants (must match training) ──────────────────────────────────────────
CHANNELS = ["temperature_c", "humidity_pct", "wind_speed_kmh",
            "precipitation_mm", "pm25", "pm10"]
N_CHANNELS = len(CHANNELS)
WINDOW_SIZE = 50
HIDDEN_SIZE = 64
LATENT_SIZE = 16
NUM_LAYERS = 2
DROPOUT = 0.2

CITY_NAMES = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]

MODELS_DIR = Path(__file__).parent / "models"

# ── Model definition (duplicated here so the Space is self-contained) ────────

class LSTMEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.lstm = nn.LSTM(N_CHANNELS, HIDDEN_SIZE, NUM_LAYERS,
                            dropout=DROPOUT, batch_first=True)
        self.dropout = nn.Dropout(DROPOUT)
        self.fc = nn.Linear(HIDDEN_SIZE, LATENT_SIZE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(x)
        return self.fc(self.dropout(hidden[-1]))


class LSTMDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc_in = nn.Linear(LATENT_SIZE, HIDDEN_SIZE)
        self.lstm = nn.LSTM(HIDDEN_SIZE, HIDDEN_SIZE, NUM_LAYERS,
                            dropout=DROPOUT, batch_first=True)
        self.fc_out = nn.Linear(HIDDEN_SIZE, N_CHANNELS)

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        h = self.fc_in(latent)
        repeated = h.unsqueeze(1).repeat(1, WINDOW_SIZE, 1)
        out, _ = self.lstm(repeated)
        return self.fc_out(out)


class LSTMAutoencoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = LSTMEncoder()
        self.decoder = LSTMDecoder()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


# ── Model registry loaded at startup ─────────────────────────────────────────

class ModelBundle:
    """Holds a trained model, its scaler, and its anomaly threshold."""
    def __init__(self, model: LSTMAutoencoder, scaler: Any, threshold: float, city: str) -> None:
        self.model = model
        self.scaler = scaler
        self.threshold = threshold
        self.city = city


_registry: Dict[str, ModelBundle] = {}
_load_errors: Dict[str, str] = {}


def load_models() -> None:
    """Loads all city models from MODELS_DIR at server startup."""
    for city in CITY_NAMES:
        slug = city.lower()
        model_path = MODELS_DIR / f"{slug}_lstm.pt"
        scaler_path = MODELS_DIR / f"{slug}_scaler.pkl"

        if not model_path.exists() or not scaler_path.exists():
            msg = f"files not found: pt={model_path.exists()} pkl={scaler_path.exists()}"
            logger.warning("[%s] %s", city, msg)
            _load_errors[city] = msg
            continue

        try:
            checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
            model = LSTMAutoencoder()
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()

            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)

            threshold = checkpoint["threshold"]
            _registry[city] = ModelBundle(model, scaler, threshold, city)
            logger.info("[%s] Model loaded — threshold=%.6f", city, threshold)
        except Exception as e:
            logger.error("[%s] Failed to load model: %s", city, e)
            _load_errors[city] = str(e)

    logger.info("Models loaded: %d / %d", len(_registry), len(CITY_NAMES))


# ── FSM + visit score (self-contained, no Redis dependency on HF) ─────────────

PEAK_HOUR_START, PEAK_HOUR_END = 10, 16
PENALTY = {"NORMAL": 0, "SUSPICIOUS": 10, "ALERT": 20, "CONFIRMED": 35}

_fsm_state: Dict[str, Dict[str, Any]] = {}


def _get_fsm(city: str) -> Dict[str, Any]:
    return _fsm_state.get(city, {"state": "NORMAL", "consec_above": 0, "consec_below": 0})


def _update_fsm(city: str, score: float, threshold: float) -> str:
    s = _get_fsm(city)
    current = s["state"]
    above = score > threshold
    above_confirmed = score > threshold * 1.5

    if above:
        s["consec_above"] = s.get("consec_above", 0) + 1
        s["consec_below"] = 0
    else:
        s["consec_below"] = s.get("consec_below", 0) + 1
        s["consec_above"] = 0

    new_state = current
    if not above and s["consec_below"] >= 5:
        new_state = "NORMAL"
    elif current == "NORMAL" and above:
        new_state = "SUSPICIOUS"
    elif current == "SUSPICIOUS" and above and s["consec_above"] >= 3:
        new_state = "ALERT"
    elif current == "ALERT" and above_confirmed and s["consec_above"] >= 5:
        new_state = "CONFIRMED"

    s["state"] = new_state
    _fsm_state[city] = s
    return new_state


def _visit_score(score: float, threshold: float, state: str) -> int:
    from datetime import datetime, timezone
    normalized = min(score / max(threshold, 1e-9), 2.0)
    base = 100 - (normalized * 40)
    penalty = PENALTY.get(state, 0)
    hour = datetime.now(timezone.utc).hour
    bonus = 10 if PEAK_HOUR_START <= hour < PEAK_HOUR_END else 0
    return int(max(0, min(100, round(base - penalty + bonus))))


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CityPulse Switzerland — Inference API",
    description="LSTM Autoencoder anomaly detection for 8 Swiss cities",
    version="2.0.0",
)


@app.on_event("startup")
async def startup_event() -> None:
    load_models()


# ── Request / Response schemas ────────────────────────────────────────────────

class PredictRequest(BaseModel):
    city: str
    window: List[List[float]]

    @field_validator("window")
    @classmethod
    def validate_window(cls, v: List[List[float]]) -> List[List[float]]:
        if len(v) < 1:
            raise ValueError("window must contain at least 1 row")
        for row in v:
            if len(row) != N_CHANNELS:
                raise ValueError(f"Each row must have exactly {N_CHANNELS} values")
        return v


class PredictResponse(BaseModel):
    city: str
    anomaly_score: float
    fsm_state: str
    visit_score: int
    threshold: float
    channel_contributions: Dict[str, float]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> Dict[str, Any]:
    """Liveness probe."""
    models_dir_files = sorted(str(p.name) for p in MODELS_DIR.glob("*")) if MODELS_DIR.exists() else []
    return {
        "status": "ok",
        "models_loaded": len(_registry),
        "cities_ready": list(_registry.keys()),
        "models_dir": str(MODELS_DIR),
        "models_dir_exists": MODELS_DIR.exists(),
        "models_dir_files": models_dir_files,
        "load_errors": _load_errors,
    }


@app.get("/cities")
async def cities() -> Dict[str, Any]:
    """Lists all supported cities and their model availability."""
    return {
        "cities": [
            {"name": c, "model_loaded": c in _registry}
            for c in CITY_NAMES
        ]
    }


@app.get("/models")
async def models_info() -> Dict[str, Any]:
    """Returns loaded model metadata (threshold per city)."""
    return {
        "models": {
            city: {"threshold": bundle.threshold, "window_size": WINDOW_SIZE}
            for city, bundle in _registry.items()
        }
    }


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    """Runs LSTM Autoencoder inference for one city.

    Accepts a sensor window and returns anomaly score, FSM state, visit score,
    and per-channel contributions.
    """
    city = request.city

    if city not in _registry:
        raise HTTPException(
            status_code=404,
            detail=f"No model loaded for city '{city}'. Available: {list(_registry.keys())}",
        )

    bundle = _registry[city]
    raw_window = np.array(request.window, dtype=np.float32)

    # Pad or trim window to WINDOW_SIZE
    if len(raw_window) < WINDOW_SIZE:
        pad = np.tile(raw_window[0], (WINDOW_SIZE - len(raw_window), 1))
        raw_window = np.vstack([pad, raw_window])
    elif len(raw_window) > WINDOW_SIZE:
        raw_window = raw_window[-WINDOW_SIZE:]

    # Normalise with fitted scaler
    scaled = bundle.scaler.transform(raw_window)
    tensor = torch.tensor(scaled, dtype=torch.float32).unsqueeze(0)  # (1, 50, 6)

    with torch.no_grad():
        recon = bundle.model(tensor)
        sq_err = (tensor - recon) ** 2
        anomaly_score = float(sq_err.mean().item())
        contributions = {
            ch: float(sq_err[0, :, i].mean().item())
            for i, ch in enumerate(CHANNELS)
        }

    fsm_state = _update_fsm(city, anomaly_score, bundle.threshold)
    visit_score = _visit_score(anomaly_score, bundle.threshold, fsm_state)

    return PredictResponse(
        city=city,
        anomaly_score=round(anomaly_score, 6),
        fsm_state=fsm_state,
        visit_score=visit_score,
        threshold=round(bundle.threshold, 6),
        channel_contributions={k: round(v, 6) for k, v in contributions.items()},
    )
