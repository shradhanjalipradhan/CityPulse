"""
02_Anomaly_Alert.py — Real-Time Anomaly Alert page.
Shows 6-channel sensor time series, anomaly score chart, FSM state
timeline, and per-channel contribution breakdown.
Auto-refreshes every 300 seconds via JavaScript reload.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import time
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    layout="wide",
    page_title="Anomaly Alert — CityPulse",
    page_icon="🚨",
    initial_sidebar_state="expanded",
)

from components.city_sidebar import render_sidebar, FSM_DOT
from components.sensor_chart import render_sensor_chart, render_anomaly_score_chart
from components.fsm_timeline import render_fsm_timeline, render_channel_contributions
from utils.redis_reader import get_all_city_states, get_city_state
from utils.supabase_reader import get_sensor_history, get_anomaly_history

REFRESH_SECONDS = 300


def main() -> None:
    # Sidebar
    all_states = get_all_city_states()
    city = render_sidebar(all_states)

    # Current state from Redis
    state = get_city_state(city)
    fsm_state = state.get("fsm_state", "NORMAL") if state else "NORMAL"
    threshold = state.get("threshold") if state else None
    dot = FSM_DOT.get(fsm_state, "⚪")

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_status = st.columns([3, 1])
    with col_title:
        st.markdown(f"## Real-Time Anomaly Monitor — {city}")
    with col_status:
        st.markdown(f"**FSM State:** {dot} `{fsm_state}`")
        st.caption(f"Threshold: {threshold:.4f}" if threshold else "Threshold: loading…")

    st.divider()

    # ── Load historical data ──────────────────────────────────────────────────
    with st.spinner("Loading 24-hour sensor history…"):
        sensor_df  = get_sensor_history(city, hours=24)
        anomaly_df = get_anomaly_history(city, hours=24)

    if sensor_df is None or sensor_df.empty:
        st.warning(
            f"No sensor data available for {city} in the last 24 hours. "
            "Ensure the Airflow pipeline is running."
        )
    if anomaly_df is None or anomaly_df.empty:
        st.warning(
            f"No anomaly scores found for {city} yet. "
            "The inference engine needs at least one pipeline run."
        )

    # ── Section 1: 6-channel sensor chart ────────────────────────────────────
    st.markdown("### 6-Channel Sensor Time Series")
    sensor_fig = render_sensor_chart(sensor_df)
    st.plotly_chart(sensor_fig, use_container_width=True)

    # ── Section 2: Anomaly score chart ───────────────────────────────────────
    st.markdown("### Anomaly Score")
    score_fig = render_anomaly_score_chart(anomaly_df, threshold=threshold)
    st.plotly_chart(score_fig, use_container_width=True)

    # ── Section 3: FSM timeline ───────────────────────────────────────────────
    st.markdown("### FSM State Timeline")
    fsm_fig = render_fsm_timeline(anomaly_df)
    st.plotly_chart(fsm_fig, use_container_width=True)

    # ── Section 4: Channel contributions ─────────────────────────────────────
    st.markdown("### Channel Contributions (Latest Window)")
    contrib_fig = render_channel_contributions(anomaly_df)
    st.plotly_chart(contrib_fig, use_container_width=True)

    # ── Recent anomaly table ──────────────────────────────────────────────────
    if anomaly_df is not None and not anomaly_df.empty:
        st.markdown("### Recent Anomaly Scores")
        display_cols = [c for c in [
            "timestamp", "anomaly_score", "fsm_state", "visit_score"
        ] if c in anomaly_df.columns]
        recent = anomaly_df[display_cols].sort_values("timestamp", ascending=False).head(10)
        recent["timestamp"] = recent["timestamp"].dt.strftime("%Y-%m-%d %H:%M UTC")
        st.dataframe(recent, use_container_width=True, hide_index=True)

    # ── Auto-refresh countdown ────────────────────────────────────────────────
    st.divider()
    col_refresh, col_btn = st.columns([3, 1])
    with col_refresh:
        # JavaScript countdown + auto-reload after REFRESH_SECONDS
        components.html(
            f"""
            <div id="cp-countdown" style="font-size:13px; color:#666; padding:4px 0;"></div>
            <script>
            var secs = {REFRESH_SECONDS};
            var timer = setInterval(function() {{
                secs--;
                var m = Math.floor(secs / 60);
                var s = secs % 60;
                var pad = s < 10 ? '0' : '';
                document.getElementById('cp-countdown').innerHTML =
                    'Auto-refresh in ' + m + ':' + pad + s;
                if (secs <= 0) {{
                    clearInterval(timer);
                    window.parent.location.reload();
                }}
            }}, 1000);
            </script>
            """,
            height=30,
        )
    with col_btn:
        if st.button("Refresh Now", use_container_width=True):
            st.rerun()

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    st.caption(f"Data loaded at {now} · Updates every 5 min from Airflow pipeline")


main()
