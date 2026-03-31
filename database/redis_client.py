"""
redis_client.py — Upstash Redis client for CityPulse using the REST API (plain requests).
Do NOT use redis-py — Upstash REST API is used instead.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.cities_config import CITY_NAMES

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class RedisClient:
    """Wraps the Upstash Redis REST API for CityPulse state caching."""

    def __init__(self) -> None:
        """Initialises the Upstash REST client from environment variables."""
        self.base_url: str = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/").strip('"')
        self.token: str = os.environ["UPSTASH_REDIS_REST_TOKEN"].strip('"')
        self.headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _request(self, *args: Any) -> Any:
        """Sends a command to the Upstash Redis REST API.

        Args:
            *args: Redis command parts (e.g. "SET", "key", "value").

        Returns:
            The 'result' field from the API response, or None on failure.
        """
        url = f"{self.base_url}/{'/'.join(str(a) for a in args)}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json().get("result")
        except requests.RequestException as e:
            logger.error("Upstash request failed (%s): %s", args[0], e)
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Stores a JSON-serialised value in Redis with an optional TTL.

        Args:
            key: Redis key.
            value: Python object — will be JSON-serialised.
            ttl_seconds: Optional expiry in seconds.

        Returns:
            True on success, False on failure.
        """
        json_value = json.dumps(value)
        if ttl_seconds:
            result = self._request("SET", key, json_value, "EX", ttl_seconds)
        else:
            result = self._request("SET", key, json_value)
        success = result == "OK"
        if not success:
            logger.error("SET failed for key: %s", key)
        return success

    def get(self, key: str) -> Optional[Any]:
        """Retrieves and deserialises a JSON value from Redis.

        Args:
            key: Redis key.

        Returns:
            Deserialised Python object, or None if the key is missing or on error.
        """
        raw = self._request("GET", key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Failed to deserialise value for key %s: %s", key, e)
            return None

    def set_city_state(self, city: str, state_dict: Dict[str, Any]) -> bool:
        """Stores the FSM state and visit score for a city.

        Args:
            city: City name.
            state_dict: Dict containing at minimum 'fsm_state' and 'visit_score'.

        Returns:
            True on success, False on failure.
        """
        key = f"city:{city}:state"
        return self.set(key, state_dict, ttl_seconds=600)

    def get_city_state(self, city: str) -> Optional[Dict[str, Any]]:
        """Retrieves the current FSM state dict for a city.

        Args:
            city: City name.

        Returns:
            State dict, or None if not cached.
        """
        key = f"city:{city}:state"
        return self.get(key)

    def get_all_city_states(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Retrieves current FSM state dicts for all 8 Swiss cities.

        Returns:
            Dict mapping city name to its state dict (or None if not cached).
        """
        return {city: self.get_city_state(city) for city in CITY_NAMES}

    def get_all_city_latest_readings(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Retrieves the latest sensor reading for all 8 Swiss cities.

        These are the keys written by the Kafka consumer:
        city:{city_name}:latest_reading

        Returns:
            Dict mapping city name to its latest reading dict (or None if not cached).
        """
        return {city: self.get(f"city:{city}:latest_reading") for city in CITY_NAMES}

    def list_all_keys(self) -> list:
        """Scans Upstash Redis and returns all currently stored keys.

        Uses the SCAN command to safely iterate without blocking.

        Returns:
            List of all key strings present in Redis.
        """
        all_keys = []
        cursor = "0"
        while True:
            result = self._request("SCAN", cursor, "COUNT", "100")
            if result is None:
                break
            # SCAN returns [next_cursor, [keys...]]
            cursor, keys = result[0], result[1]
            all_keys.extend(keys)
            if str(cursor) == "0":
                break
        return all_keys


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Redis Client")
    parser.add_argument("--test", action="store_true", help="Check latest_reading keys for all 8 cities")
    parser.add_argument("--debug", action="store_true", help="List every key in Redis with its value")
    args = parser.parse_args()

    client = RedisClient()

    if args.debug or args.test:
        print("\n--- All keys currently in Redis ---")
        keys = client.list_all_keys()
        if not keys:
            print("  (no keys found)")
        else:
            for key in sorted(keys):
                val = client.get(key)
                print(f"  {key} => {val}")
        print(f"\nTotal keys: {len(keys)}\n")

    if args.test:
        print("--- city:*:latest_reading check ---")
        readings = client.get_all_city_latest_readings()
        found = sum(1 for v in readings.values() if v is not None)
        for city, reading in readings.items():
            if reading:
                temp = reading.get("temperature_c", "?")
                ts = reading.get("timestamp", "?")
                print(f"  {city}: OK  (temp={temp}°C  ts={ts})")
            else:
                print(f"  {city}: NOT FOUND")
        print(f"\nAll {found} city states found in Redis")
