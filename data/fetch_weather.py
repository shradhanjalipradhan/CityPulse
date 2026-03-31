"""
fetch_weather.py — Fetches current and historical weather data from OpenMeteo (free, no API key).
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import requests
import pandas as pd

from data.cities_config import SWISS_CITIES

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5


class FetchWeather:
    """Fetches current and historical weather for Swiss cities using OpenMeteo API."""

    def _get(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Makes a GET request with retry logic.

        Args:
            url: The endpoint URL.
            params: Query parameters.

        Returns:
            Parsed JSON response dict, or None on failure.
        """
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                logger.warning(
                    "Attempt %d/%d failed for %s: %s", attempt, RETRY_ATTEMPTS, url, e
                )
                if attempt < RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS)
        logger.error("All %d attempts failed for %s", RETRY_ATTEMPTS, url)
        return None

    def fetch_current(self, city: str) -> Optional[Dict[str, float]]:
        """Fetches current weather conditions for a city.

        Args:
            city: City name matching a key in SWISS_CITIES.

        Returns:
            Dict with keys: temperature_c, humidity_pct, wind_speed_kmh, precipitation_mm.
            Returns None if the city is unknown or the request fails.
        """
        if city not in SWISS_CITIES:
            logger.error("Unknown city: %s", city)
            return None

        coords = SWISS_CITIES[city]
        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
            "wind_speed_unit": "kmh",
            "timezone": "Europe/Zurich",
        }

        logger.info("[%s] Fetching current weather at %s", city, datetime.utcnow().isoformat())
        data = self._get(OPENMETEO_URL, params)
        if data is None:
            return None

        current = data.get("current", {})
        result = {
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
        }
        logger.info("[%s] Weather fetched: %s", city, result)
        return result

    def fetch_historical(self, city: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Fetches historical weather data for model training.

        Args:
            city: City name matching a key in SWISS_CITIES.
            days: Number of past days to retrieve (default 30).

        Returns:
            DataFrame with columns: timestamp, temperature_c, humidity_pct,
            wind_speed_kmh, precipitation_mm. Returns None on failure.
        """
        if city not in SWISS_CITIES:
            logger.error("Unknown city: %s", city)
            return None

        coords = SWISS_CITIES[city]
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
            "wind_speed_unit": "kmh",
            "timezone": "Europe/Zurich",
        }

        logger.info(
            "[%s] Fetching historical weather from %s to %s",
            city, start_date, end_date,
        )
        data = self._get(OPENMETEO_HISTORICAL_URL, params)
        if data is None:
            return None

        hourly = data.get("hourly", {})
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly.get("time", [])),
            "temperature_c": hourly.get("temperature_2m", []),
            "humidity_pct": hourly.get("relative_humidity_2m", []),
            "wind_speed_kmh": hourly.get("wind_speed_10m", []),
            "precipitation_mm": hourly.get("precipitation", []),
        })
        logger.info("[%s] Historical weather fetched: %d rows", city, len(df))
        return df
