"""
inference_engine.py — Reads latest sensor windows from Supabase, calls the
HuggingFace /predict endpoint, and writes anomaly scores + FSM state back
to Supabase and Redis.

Usage:
  python models/inference_engine.py           # run all 8 cities
  python models/inference_engine.py --test    # dry-run with dummy data
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from data.cities_config import CITY_NAMES
from database.supabase_client import SupabaseClient
from database.redis_client import RedisClient
from models.lstm_autoencoder import CHANNELS, WINDOW_SIZE

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HF_USERNAME = os.environ["HF_USERNAME"]
HF_SPACE_NAME = os.environ["HF_SPACE_NAME"]
HF_ENDPOINT = f"https://{HF_USERNAME}-{HF_SPACE_NAME}.hf.space"
REQUEST_TIMEOUT = 30


class InferenceEngine:
    """Orchestrates end-to-end inference: Supabase → HF → Supabase + Redis."""

    def __init__(self) -> None:
        self.supabase = SupabaseClient()
        self.redis = RedisClient()

    def get_city_window(self, city: str) -> Optional[List[List[float]]]:
        """Reads the last WINDOW_SIZE sensor readings for a city from Supabase.

        Args:
            city: City name.

        Returns:
            List of WINDOW_SIZE rows, each a list of 6 floats matching CHANNELS.
            Returns None if insufficient data.
        """
        df = self.supabase.get_recent_readings(city, limit=WINDOW_SIZE)
        if df is None or len(df) == 0:
            logger.warning("[%s] No readings available", city)
            return None
        if len(df) < WINDOW_SIZE:
            logger.warning(
                "[%s] Only %d readings available (need %d) — padding with first row",
                city, len(df), WINDOW_SIZE,
            )

        df = df.sort_values("timestamp").tail(WINDOW_SIZE)

        # Fill any missing channel values with column medians
        for col in CHANNELS:
            if col not in df.columns:
                df[col] = 0.0
        df[CHANNELS] = df[CHANNELS].fillna(df[CHANNELS].median())

        rows = df[CHANNELS].values.tolist()
        # Pad to WINDOW_SIZE by repeating the first row at the front
        if len(rows) < WINDOW_SIZE:
            pad = [rows[0]] * (WINDOW_SIZE - len(rows))
            rows = pad + rows
        return rows

    def call_predict(self, city: str, window: List[List[float]]) -> Optional[Dict[str, Any]]:
        """Posts a sensor window to the HuggingFace /predict endpoint.

        Args:
            city: City name.
            window: List of WINDOW_SIZE × 6 floats.

        Returns:
            Response dict with anomaly_score, fsm_state, visit_score, etc.
            Returns None on failure.
        """
        url = f"{HF_ENDPOINT}/predict"
        payload = {"city": city, "window": window}
        try:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("[%s] HF predict call failed: %s", city, e)
            return None

    def write_results(self, city: str, result: Dict[str, Any]) -> None:
        """Persists inference results to Supabase anomaly_scores and Redis.

        Args:
            city: City name.
            result: Response dict from /predict endpoint.
        """
        contributions = result.get("channel_contributions", {})
        score_row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "anomaly_score": result.get("anomaly_score"),
            "fsm_state": result.get("fsm_state", "NORMAL"),
            "visit_score": result.get("visit_score", 100),
            "temp_contribution": contributions.get("temperature_c"),
            "humidity_contribution": contributions.get("humidity_pct"),
            "wind_contribution": contributions.get("wind_speed_kmh"),
            "precip_contribution": contributions.get("precipitation_mm"),
            "pm25_contribution": contributions.get("pm25"),
            "pm10_contribution": contributions.get("pm10"),
        }
        self.supabase.insert_anomaly_score(city, score_row)

        redis_payload = {
            "fsm_state": result.get("fsm_state", "NORMAL"),
            "visit_score": result.get("visit_score", 100),
            "anomaly_score": result.get("anomaly_score"),
            "threshold": result.get("threshold"),
            "timestamp": score_row["timestamp"],
        }
        self.redis.set_city_state(city, redis_payload)

        logger.info(
            "[%s] score=%.4f state=%s visit=%d",
            city,
            result.get("anomaly_score", 0),
            result.get("fsm_state", "?"),
            result.get("visit_score", 0),
        )

    def run_city(self, city: str) -> Optional[Dict[str, Any]]:
        """Runs the full inference pipeline for one city.

        Args:
            city: City name.

        Returns:
            Result dict from /predict, or None on failure.
        """
        window = self.get_city_window(city)
        if window is None:
            return None

        result = self.call_predict(city, window)
        if result is None:
            return None

        self.write_results(city, result)
        return result

    def run_all_cities(self) -> Dict[str, Any]:
        """Runs inference for all 8 Swiss cities.

        Returns:
            Dict mapping city name to its result dict (or None on failure).
        """
        results = {}
        for city in CITY_NAMES:
            try:
                results[city] = self.run_city(city)
            except Exception as e:
                logger.error("[%s] Unexpected error during inference: %s", city, e)
                results[city] = None
        return results

    def health_check(self) -> bool:
        """Checks that the HuggingFace Space is reachable.

        Returns:
            True if /health returns 200, False otherwise.
        """
        try:
            r = requests.get(f"{HF_ENDPOINT}/health", timeout=10)
            ok = r.status_code == 200
            logger.info("HF Space health: %s", "OK" if ok else f"FAIL ({r.status_code})")
            return ok
        except requests.RequestException as e:
            logger.error("HF Space unreachable: %s", e)
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Inference Engine")
    parser.add_argument("--test", action="store_true",
                        help="Dry-run: check HF health and print window shapes only")
    args = parser.parse_args()

    engine = InferenceEngine()

    print(f"\nHuggingFace endpoint: {HF_ENDPOINT}")

    if args.test:
        print("\n--- Health check ---")
        ok = engine.health_check()
        print(f"HF Space: {'ONLINE' if ok else 'OFFLINE'}")
        print("\n--- Supabase window availability ---")
        for city in CITY_NAMES:
            window = engine.get_city_window(city)
            status = f"{len(window)} rows ready" if window else "NOT ENOUGH DATA"
            print(f"  {city}: {status}")
    else:
        print("\nRunning inference for all 8 cities...\n")
        results = engine.run_all_cities()
        print("\n--- Results ---")
        for city, r in results.items():
            if r:
                print(f"  {city}: score={r.get('anomaly_score', '?'):.4f}  "
                      f"state={r.get('fsm_state', '?')}  "
                      f"visit={r.get('visit_score', '?')}")
            else:
                print(f"  {city}: FAILED")
