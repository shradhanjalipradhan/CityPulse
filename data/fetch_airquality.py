"""
fetch_airquality.py — Fetches current and historical air quality (PM2.5, PM10)
from the OpenAQ v3 free API.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.cities_config import SWISS_CITIES

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_OPENAQ_API_KEY: str = os.getenv("OPENAQ_API_KEY", "")

OPENAQ_LOCATIONS_URL = "https://api.openaq.org/v3/locations"
OPENAQ_LOCATION_LATEST_URL = "https://api.openaq.org/v3/locations/{}/latest"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5

# Fallback nearest station mapping for cities with sparse coverage
FALLBACK_CITIES = {"Zermatt", "Interlaken"}

# Estimated baseline values used when no station data is available
ESTIMATED_FALLBACK = {"pm25": 5.0, "pm10": 10.0}


class FetchAirQuality:
    """Fetches current and historical air quality data for Swiss cities using OpenAQ v3."""

    def _get(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Makes a GET request with retry logic.

        Args:
            url: The endpoint URL.
            params: Query parameters.

        Returns:
            Parsed JSON response dict, or None on failure.
        """
        headers = {"X-API-Key": _OPENAQ_API_KEY} if _OPENAQ_API_KEY else {}
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
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

    def _find_nearest_location_id(self, city: str, parameter: str = "pm25") -> Optional[int]:
        """Finds the nearest OpenAQ station that measures a given parameter.

        Searches up to 100km in expanding rings until a station is found.

        Args:
            city: City name matching a key in SWISS_CITIES.
            parameter: OpenAQ parameter name to filter by (default 'pm25').

        Returns:
            OpenAQ location ID, or None if no station found within range.
        """
        coords = SWISS_CITIES[city]
        for radius in (25000, 50000, 100000):
            params = {
                "coordinates": f"{coords['lat']},{coords['lon']}",
                "radius": radius,
                "limit": 10,
                "parameter": parameter,
            }
            data = self._get(OPENAQ_LOCATIONS_URL, params)
            if data and data.get("results"):
                logger.info("[%s] Found PM station within %dm radius", city, radius)
                return data["results"][0].get("id")
        return None

    def _get_pm_location(self, city: str) -> Optional[Dict]:
        """Finds the nearest location that has pm25 or pm10 sensors with current data.

        Iterates through candidate locations until one with PM sensors is found.

        Args:
            city: City name matching a key in SWISS_CITIES.

        Returns:
            Location dict (including its sensors list), or None if none found.
        """
        coords = SWISS_CITIES[city]
        params = {
            "coordinates": f"{coords['lat']},{coords['lon']}",
            "radius": 25000,
            "limit": 10,
            "parameter": "pm25",
        }
        data = self._get(OPENAQ_LOCATIONS_URL, params)
        if data:
            for loc in data.get("results", []):
                sensors = loc.get("sensors", [])
                pm_sensors = [
                    s for s in sensors
                    if s.get("parameter", {}).get("name") in ("pm25", "pm10")
                ]
                if pm_sensors:
                    return loc
        return None

    def fetch_current(self, city: str) -> Dict[str, Optional[float]]:
        """Fetches current PM2.5 and PM10 readings for a city.

        Finds the nearest station with PM sensors, builds a sensor_id → parameter
        map from the location detail, then reads the latest values.
        Falls back to estimated values if no station data is available.

        Args:
            city: City name matching a key in SWISS_CITIES.

        Returns:
            Dict with keys: pm25, pm10. Values may be estimated floats.
        """
        if city not in SWISS_CITIES:
            logger.error("Unknown city: %s", city)
            return ESTIMATED_FALLBACK.copy()

        logger.info("[%s] Fetching current air quality at %s", city, datetime.utcnow().isoformat())

        location = self._get_pm_location(city)
        if location is None:
            logger.warning("[%s] No PM station found — using estimated values", city)
            return ESTIMATED_FALLBACK.copy()

        location_id = location["id"]

        # Build sensor_id → parameter_name map from the location's sensors list
        sensor_param_map: Dict[int, str] = {
            s["id"]: s["parameter"]["name"]
            for s in location.get("sensors", [])
            if "parameter" in s
        }

        # Fetch latest readings (returns sensorsId + value, no parameter name)
        latest = self._get(OPENAQ_LOCATION_LATEST_URL.format(location_id), {})
        result: Dict[str, Optional[float]] = {"pm25": None, "pm10": None}

        if latest and latest.get("results"):
            for reading in latest["results"]:
                sid = reading.get("sensorsId")
                param = sensor_param_map.get(sid)
                value = reading.get("value")
                if param == "pm25" and result["pm25"] is None and value is not None:
                    result["pm25"] = float(value)
                elif param == "pm10" and result["pm10"] is None and value is not None:
                    result["pm10"] = float(value)

        # Fill any missing parameters with estimates
        if result["pm25"] is None:
            result["pm25"] = ESTIMATED_FALLBACK["pm25"]
            logger.warning("[%s] pm25 not found — using estimate", city)
        if result["pm10"] is None:
            result["pm10"] = ESTIMATED_FALLBACK["pm10"]
            logger.warning("[%s] pm10 not found — using estimate", city)

        logger.info("[%s] Air quality fetched: %s", city, result)
        return result

    def fetch_historical(self, city: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Fetches historical air quality data for model training.

        Args:
            city: City name matching a key in SWISS_CITIES.
            days: Number of past days to retrieve (default 30).

        Returns:
            DataFrame with columns: timestamp, pm25, pm10. Returns None on failure.
        """
        if city not in SWISS_CITIES:
            logger.error("Unknown city: %s", city)
            return None

        location_id = self._find_nearest_location_id(city)
        if location_id is None:
            logger.warning("[%s] No AQ station found for historical fetch", city)
            return None

        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "location_id": location_id,
            "parameter": ["pm25", "pm10"],
            "date_from": date_from,
            "date_to": date_to,
            "limit": 1000,
            "order_by": "datetime",
        }

        # Get the location detail to find pm25/pm10 sensor IDs
        loc_data = self._get(f"{OPENAQ_LOCATIONS_URL}/{location_id}", {})
        if not loc_data or not loc_data.get("results"):
            return None

        sensors = loc_data["results"][0].get("sensors", [])
        pm_sensors = {
            s["parameter"]["name"]: s["id"]
            for s in sensors
            if s.get("parameter", {}).get("name") in ("pm25", "pm10")
        }
        if not pm_sensors:
            logger.warning("[%s] No pm25/pm10 sensors at location %d", city, location_id)
            return None

        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        all_rows = []
        for param_name, sensor_id in pm_sensors.items():
            sensor_url = f"https://api.openaq.org/v3/sensors/{sensor_id}/measurements"
            params = {
                "date_from": date_from,
                "date_to": date_to,
                "limit": 1000,
                "period_name": "hour",
            }
            logger.info("[%s] Fetching historical air quality (%d days)", city, days)
            data = self._get(sensor_url, params)
            if data and data.get("results"):
                for reading in data["results"]:
                    ts = reading.get("period", {}).get("datetimeTo", {}).get("utc") \
                         or reading.get("date", {}).get("utc")
                    all_rows.append({
                        "timestamp": ts,
                        "parameter": param_name,
                        "value": reading.get("value"),
                    })

        if not all_rows:
            return None

        df_raw = pd.DataFrame(all_rows)
        df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
        df_pivot = df_raw.pivot_table(
            index="timestamp", columns="parameter", values="value", aggfunc="mean"
        ).reset_index()
        df_pivot.columns.name = None

        for col in ["pm25", "pm10"]:
            if col not in df_pivot.columns:
                df_pivot[col] = None

        logger.info("[%s] Historical AQ fetched: %d rows", city, len(df_pivot))
        return df_pivot[["timestamp", "pm25", "pm10"]]


if __name__ == "__main__":
    from data.cities_config import CITY_NAMES
    fetcher = FetchAirQuality()
    print(f"\nOpenAQ API key loaded: {'YES' if _OPENAQ_API_KEY else 'NO (will use estimates)'}\n")
    for city in CITY_NAMES:
        result = fetcher.fetch_current(city)
        print(f"  {city}: pm25={result['pm25']}  pm10={result['pm10']}")
