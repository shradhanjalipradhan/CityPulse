"""
train_models.py — Trains one LSTM Autoencoder per Swiss city.

For each city:
  1. Fetches 30 days of historical weather (OpenMeteo) + air quality (OpenAQ)
  2. Merges, forward-fills, normalises with StandardScaler
  3. Creates sliding windows (size=50, stride=1)
  4. Splits 70/15/15 (no shuffle — time-series)
  5. Trains LSTMAutoencoder for 60 epochs with early stopping
  6. Sets threshold = 95th percentile of validation reconstruction errors
  7. Saves {city}_lstm.pt and {city}_scaler.pkl to models/saved_models/

Usage:
  python models/train_models.py
"""

import logging
import os
import pickle
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.cities_config import CITY_NAMES
from data.fetch_weather import FetchWeather
from data.fetch_airquality import FetchAirQuality
from models.lstm_autoencoder import LSTMAutoencoder, CHANNELS, WINDOW_SIZE

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SAVED_MODELS_DIR = Path(__file__).parent / "saved_models"
EPOCHS = 60
BATCH_SIZE = 32
LEARNING_RATE = 1e-3
PATIENCE = 10          # early stopping patience
THRESHOLD_PERCENTILE = 95
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
HISTORICAL_DAYS = 30


def fetch_training_data(city: str) -> pd.DataFrame:
    """Fetches and merges 30-day historical weather and air quality for a city.

    Args:
        city: City name.

    Returns:
        DataFrame with columns matching CHANNELS, indexed by hour.
        Missing values forward-filled, then backfilled.
    """
    weather_fetcher = FetchWeather()
    aq_fetcher = FetchAirQuality()

    logger.info("[%s] Fetching historical weather...", city)
    weather_df = weather_fetcher.fetch_historical(city, days=HISTORICAL_DAYS)

    logger.info("[%s] Fetching historical air quality...", city)
    aq_df = aq_fetcher.fetch_historical(city, days=HISTORICAL_DAYS)

    if weather_df is None or weather_df.empty:
        raise RuntimeError(f"[{city}] No weather data available")

    weather_df = weather_df.set_index("timestamp").sort_index()

    if aq_df is not None and not aq_df.empty:
        aq_df = aq_df.set_index("timestamp").sort_index()
        # Strip tz from AQ (UTC-aware) to make it tz-naive for merging
        if aq_df.index.tz is not None:
            aq_df.index = aq_df.index.tz_localize(None)
        aq_df = aq_df.resample("h").mean()
        # Use merge_asof with 2h tolerance to bridge the UTC↔local-time offset
        merged = pd.merge_asof(
            weather_df.reset_index().sort_values("timestamp"),
            aq_df.reset_index().sort_values("timestamp"),
            on="timestamp",
            tolerance=pd.Timedelta("2h"),
            direction="nearest",
        )
        df = merged.set_index("timestamp")
    else:
        logger.warning("[%s] No AQ data — using fallback pm25=5.0, pm10=10.0", city)
        df = weather_df.copy()
        df["pm25"] = 5.0
        df["pm10"] = 10.0

    df = df[CHANNELS]
    df = df.ffill().bfill()
    # Fill any remaining NaN in pm25/pm10 with fallback rather than dropping rows
    df["pm25"] = df["pm25"].fillna(5.0)
    df["pm10"] = df["pm10"].fillna(10.0)
    # Only drop rows where core weather channels are missing
    df = df.dropna(subset=["temperature_c", "humidity_pct", "wind_speed_kmh", "precipitation_mm"])

    logger.info("[%s] Training data shape: %s", city, df.shape)
    return df


def make_windows(data: np.ndarray, window_size: int = WINDOW_SIZE) -> np.ndarray:
    """Creates overlapping sliding windows from a 2D array.

    Args:
        data: (timesteps, channels) array.
        window_size: Number of timesteps per window.

    Returns:
        (n_windows, window_size, channels) array.
    """
    n = len(data) - window_size + 1
    return np.stack([data[i: i + window_size] for i in range(n)])


def split_data(
    windows: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Splits windows into train/val/test without shuffling.

    Args:
        windows: (n_windows, window_size, channels)

    Returns:
        Tuple of (train, val, test) arrays.
    """
    n = len(windows)
    train_end = int(n * TRAIN_RATIO)
    val_end = train_end + int(n * VAL_RATIO)
    return windows[:train_end], windows[train_end:val_end], windows[val_end:]


def train_city(city: str) -> dict:
    """Trains one LSTM Autoencoder for a given city and saves artifacts.

    Args:
        city: City name.

    Returns:
        Dict with val_loss, threshold, epochs_trained, status.
    """
    SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Data ──────────────────────────────────────────────────────────────
    df = fetch_training_data(city)

    scaler = StandardScaler()
    scaled = scaler.fit_transform(df.values.astype(np.float32))

    windows = make_windows(scaled)
    if len(windows) < 10:
        raise RuntimeError(f"[{city}] Not enough data: only {len(windows)} windows")

    train_w, val_w, _ = split_data(windows)

    train_tensor = torch.tensor(train_w, dtype=torch.float32)
    val_tensor = torch.tensor(val_w, dtype=torch.float32)

    train_loader = DataLoader(TensorDataset(train_tensor), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(TensorDataset(val_tensor), batch_size=BATCH_SIZE)

    # ── 2. Model ──────────────────────────────────────────────────────────────
    model = LSTMAutoencoder(window_size=WINDOW_SIZE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None
    patience_counter = 0

    # ── 3. Training loop ──────────────────────────────────────────────────────
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss = 0.0
        for (batch,) in train_loader:
            optimizer.zero_grad()
            recon = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(batch)
        train_loss /= len(train_tensor)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for (batch,) in val_loader:
                recon = model(batch)
                loss = criterion(recon, batch)
                val_loss += loss.item() * len(batch)
        val_loss /= len(val_tensor)

        if epoch % 10 == 0 or epoch == 1:
            logger.info("[%s] Epoch %d/%d — train=%.6f val=%.6f",
                        city, epoch, EPOCHS, train_loss, val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                logger.info("[%s] Early stopping at epoch %d", city, epoch)
                break

    model.load_state_dict(best_state)

    # ── 4. Threshold ──────────────────────────────────────────────────────────
    model.eval()
    val_errors = []
    with torch.no_grad():
        for (batch,) in val_loader:
            recon = model(batch)
            errs = ((batch - recon) ** 2).mean(dim=(1, 2))
            val_errors.extend(errs.tolist())
    threshold = float(np.percentile(val_errors, THRESHOLD_PERCENTILE))

    # ── 5. Save artifacts ─────────────────────────────────────────────────────
    city_slug = city.lower()
    model_path = SAVED_MODELS_DIR / f"{city_slug}_lstm.pt"
    scaler_path = SAVED_MODELS_DIR / f"{city_slug}_scaler.pkl"

    torch.save({
        "model_state_dict": model.state_dict(),
        "threshold": threshold,
        "city": city,
        "window_size": WINDOW_SIZE,
        "channels": CHANNELS,
    }, model_path)

    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)

    logger.info(
        "[%s] Saved — val_loss=%.6f  threshold=%.6f  path=%s",
        city, best_val_loss, threshold, model_path,
    )
    return {
        "city": city,
        "val_loss": round(best_val_loss, 6),
        "threshold": round(threshold, 6),
        "status": "OK",
    }


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CityPulse Switzerland — LSTM Autoencoder Training")
    print("=" * 60)

    results = []
    for city in CITY_NAMES:
        print(f"\n>>> Training {city}...")
        try:
            result = train_city(city)
            results.append(result)
        except Exception as e:
            logger.error("[%s] Training failed: %s", city, e)
            results.append({"city": city, "val_loss": None, "threshold": None, "status": f"FAILED: {e}"})

    print("\n" + "=" * 60)
    print("Training Summary")
    print("=" * 60)
    print(f"{'City':<12} {'Val Loss':<12} {'Threshold':<12} {'Status'}")
    print("-" * 55)
    for r in results:
        vl = f"{r['val_loss']:.6f}" if r["val_loss"] is not None else "—"
        th = f"{r['threshold']:.6f}" if r["threshold"] is not None else "—"
        print(f"{r['city']:<12} {vl:<12} {th:<12} {r['status']}")
    print("=" * 60)
