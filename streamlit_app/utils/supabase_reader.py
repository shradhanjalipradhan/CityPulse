"""
supabase_reader.py — Reads historical sensor and anomaly data from
Supabase for the Streamlit dashboard.
Credentials loaded from st.secrets.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import streamlit as st
from supabase import create_client, Client

logger = logging.getLogger(__name__)


@st.cache_resource
def _client() -> Client:
    """Returns a cached Supabase client (created once per session).
    Uses service key so all rows are readable regardless of RLS.
    Key is stored server-side in Streamlit secrets — never exposed to browser.
    """
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_KEY"],
    )


def _since_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def get_anomaly_history(city: str, hours: int = 24) -> Optional[pd.DataFrame]:
    """Returns anomaly_scores rows for the last N hours for a city.

    Columns: timestamp, anomaly_score, fsm_state, visit_score,
    temp_contribution, humidity_contribution, wind_contribution,
    precip_contribution, pm25_contribution, pm10_contribution.
    """
    try:
        resp = (
            _client()
            .table("anomaly_scores")
            .select("*")
            .eq("city", city)
            .gte("timestamp", _since_iso(hours))
            .order("timestamp", desc=False)
            .execute()
        )
        if resp.data:
            df = pd.DataFrame(resp.data)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df
        return None
    except Exception as e:
        logger.error("get_anomaly_history(%s): %s", city, e)
        return None


def get_sensor_history(city: str, hours: int = 24) -> Optional[pd.DataFrame]:
    """Returns sensor_readings rows for the last N hours for a city.

    Columns: timestamp, temperature_c, humidity_pct, wind_speed_kmh,
    precipitation_mm, pm25, pm10.
    """
    try:
        resp = (
            _client()
            .table("sensor_readings")
            .select("timestamp,temperature_c,humidity_pct,wind_speed_kmh,precipitation_mm,pm25,pm10")
            .eq("city", city)
            .gte("timestamp", _since_iso(hours))
            .order("timestamp", desc=False)
            .execute()
        )
        if resp.data:
            df = pd.DataFrame(resp.data)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df
        return None
    except Exception as e:
        logger.error("get_sensor_history(%s): %s", city, e)
        return None


def get_latest_anomaly(city: str) -> Optional[dict]:
    """Returns the most recent anomaly_scores row for a city."""
    try:
        resp = (
            _client()
            .table("anomaly_scores")
            .select("*")
            .eq("city", city)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("get_latest_anomaly(%s): %s", city, e)
        return None
