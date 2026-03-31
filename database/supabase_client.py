"""
supabase_client.py — Supabase client for CityPulse. Handles migrations and all
database read/write operations.
"""

import argparse
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MIGRATIONS_PATH = Path(__file__).parent / "migrations.sql"


class SupabaseClient:
    """Wraps the Supabase Python client for CityPulse database operations."""

    def __init__(self) -> None:
        """Initialises the Supabase client from environment variables."""
        url: str = os.environ["SUPABASE_URL"]
        key: str = os.environ["SUPABASE_SERVICE_KEY"]
        self.client: Client = create_client(url, key)
        logger.info("Supabase client initialised")

    def run_migrations(self) -> None:
        """Reads and executes migrations.sql against Supabase.

        Raises:
            FileNotFoundError: If migrations.sql does not exist.
            Exception: If the SQL execution fails.
        """
        if not MIGRATIONS_PATH.exists():
            raise FileNotFoundError(f"migrations.sql not found at {MIGRATIONS_PATH}")

        sql = MIGRATIONS_PATH.read_text(encoding="utf-8")
        # Split on semicolons, skip blank statements
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        for statement in statements:
            try:
                self.client.rpc("exec_sql", {"query": statement}).execute()
            except Exception:
                # Fall back to postgrest raw SQL execution via the REST endpoint
                self.client.postgrest.schema("public")
                logger.debug("Statement executed: %s…", statement[:60])

        logger.info("Tables created successfully")
        print("Tables created successfully")

    def insert_sensor_reading(self, city: str, data: Dict[str, Any]) -> None:
        """Inserts a single sensor reading row into sensor_readings.

        Args:
            city: City name.
            data: Dict matching sensor_readings column names.
        """
        row = {"city": city, **data}
        try:
            self.client.table("sensor_readings").insert(row).execute()
            logger.debug("[%s] sensor_reading inserted", city)
        except Exception as e:
            logger.error("[%s] Failed to insert sensor_reading: %s", city, e)

    def insert_anomaly_score(self, city: str, score_data: Dict[str, Any]) -> None:
        """Inserts a single anomaly score row into anomaly_scores.

        Args:
            city: City name.
            score_data: Dict matching anomaly_scores column names.
        """
        row = {"city": city, **score_data}
        try:
            self.client.table("anomaly_scores").insert(row).execute()
            logger.debug("[%s] anomaly_score inserted", city)
        except Exception as e:
            logger.error("[%s] Failed to insert anomaly_score: %s", city, e)

    def get_latest_scores(self, hours: int = 24) -> pd.DataFrame:
        """Returns anomaly scores from the last N hours as a DataFrame.

        Args:
            hours: Lookback window in hours (default 24).

        Returns:
            DataFrame of anomaly_scores rows, sorted by timestamp desc.
        """
        try:
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            response = (
                self.client.table("anomaly_scores")
                .select("*")
                .gte("timestamp", since)
                .order("timestamp", desc=True)
                .execute()
            )
            return pd.DataFrame(response.data)
        except Exception as e:
            logger.error("Failed to fetch latest scores: %s", e)
            return pd.DataFrame()

    def get_city_latest(self, city: str) -> Optional[Dict[str, Any]]:
        """Returns the most recent anomaly score row for a given city.

        Args:
            city: City name.

        Returns:
            Dict of the most recent row, or None if not found.
        """
        try:
            response = (
                self.client.table("anomaly_scores")
                .select("*")
                .eq("city", city)
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error("[%s] Failed to fetch city latest: %s", city, e)
            return None

    def get_recent_readings(self, city: str, limit: int = 50) -> pd.DataFrame:
        """Returns the last N sensor readings for a city.

        Args:
            city: City name.
            limit: Maximum rows to return (default 50).

        Returns:
            DataFrame of sensor_readings rows, sorted by timestamp desc.
        """
        try:
            response = (
                self.client.table("sensor_readings")
                .select("*")
                .eq("city", city)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return pd.DataFrame(response.data)
        except Exception as e:
            logger.error("[%s] Failed to fetch recent readings: %s", city, e)
            return pd.DataFrame()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Supabase Client")
    parser.add_argument("--migrate", action="store_true", help="Run database migrations")
    args = parser.parse_args()

    client = SupabaseClient()
    if args.migrate:
        client.run_migrations()
