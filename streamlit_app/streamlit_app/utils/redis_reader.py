"""
redis_reader.py — Reads city state and latest sensor readings from
Upstash Redis REST API for the Streamlit dashboard.
Credentials loaded from st.secrets.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

logger = logging.getLogger(__name__)

CITY_NAMES: List[str] = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]


def _get(key: str) -> Optional[Any]:
    """Fetches a single key from Upstash Redis via REST GET.

    Returns:
        Parsed value (dict/list/str) or None if key missing / error.
    """
    try:
        url = st.secrets["UPSTASH_REDIS_URL"].rstrip("/")
        token = st.secrets["UPSTASH_REDIS_TOKEN"]
    except KeyError as e:
        logger.error("Missing Redis secret: %s", e)
        return None

    try:
        r = requests.get(
            f"{url}/get/{key}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if r.status_code == 200:
            raw = r.json().get("result")
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
    except requests.RequestException as e:
        logger.warning("Redis GET failed for key %s: %s", key, e)
    return None


def get_city_state(city: str) -> Optional[Dict]:
    """Returns the latest FSM state dict for a city.

    Keys in returned dict: fsm_state, visit_score, anomaly_score,
    threshold, timestamp.
    Written by inference_engine.py via redis_client.set_city_state().
    """
    return _get(f"city:{city}:state")


def get_all_city_states() -> Dict[str, Optional[Dict]]:
    """Returns state dicts for all 8 cities.

    Returns:
        Dict mapping city name → state dict (None if not cached).
    """
    return {city: get_city_state(city) for city in CITY_NAMES}


def get_latest_reading(city: str) -> Optional[Dict]:
    """Returns the most recent raw sensor reading for a city.

    Keys: city, timestamp, temperature_c, humidity_pct,
    wind_speed_kmh, precipitation_mm, pm25, pm10.
    Written by kafka/consumer.py on every Kafka message.
    """
    return _get(f"city:{city}:latest_reading")
