"""
02_Anomaly_Alert.py — Real-Time Anomaly Alert page.
Shows 6-channel sensor time series, anomaly score chart, FSM state
timeline, and per-channel contribution breakdown.
Auto-refreshes every 300 seconds via JavaScript reload.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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

_CSS = """
<style>
.cp-section {
    color: #00D4FF;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin: 16px 0 4px;
    padding-bottom: 4px;
    border-bottom: 1px solid #1E2740;
}
.fsm-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.fsm-NORMAL    { background:rgba(0,255,136,0.12); color:#00FF88; border:1px solid #00FF88;
                  box-shadow:0 0 8px rgba(0,255,136,0.25); }
.fsm-SUSPICIOUS{ background:rgba(255,184,0,0.12);  color:#FFB800; border:1px solid #FFB800;
                  box-shadow:0 0 8px rgba(255,184,0,0.25); }
.fsm-ALERT     { background:rgba(255,107,53,0.12); color:#FF6B35; border:1px solid #FF6B35;
                  box-shadow:0 0 8px rgba(255,107,53,0.25); }
.fsm-CONFIRMED { background:rgba(255,51,102,0.15); color:#FF3366; border:1px solid #FF3366;
                  box-shadow:0 0 8px rgba(255,51,102,0.30); }
[data-testid="stDataFrame"] { border:1px solid #1E2740; border-radius:8px; }
</style>
"""


def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    # Sidebar
    all_states = get_all_city_states()
    city = render_sidebar(all_states)

    # Current state from Redis
    state     = get_city_state(city)
    fsm_state = state.get("fsm_state", "NORMAL") if state else "NORMAL"
    threshold = state.get("threshold") if state else None

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_status = st.columns([3, 1])
    with col_title:
        st.markdown(
            f"<h2 style='color:#E8EAF0;margin:0;'>"
            f"<span style='color:#00D4FF;'>🚨</span> "
            f"Real-Time Anomaly Monitor — {city}</h2>",
            unsafe_allow_html=True,
        )
    with col_status:
        st.markdown(
            f"<b style='color:#8892A4;'>FSM State:</b>&nbsp;"
            f"<span class='fsm-badge fsm-{fsm_state}'>{fsm_state}</span>",
            unsafe_allow_html=True,
        )
        thr_text = f"{threshold:.4f}" if threshold else "loading…"
        st.caption(f"Threshold: {thr_text}")

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
    st.markdown("<div class='cp-section'>6-Channel Sensor Time Series</div>", unsafe_allow_html=True)
    sensor_fig = render_sensor_chart(sensor_df)
    st.plotly_chart(sensor_fig, use_container_width=True)

    # ── Section 2: Anomaly score chart ───────────────────────────────────────
    st.markdown("<div class='cp-section'>Anomaly Score</div>", unsafe_allow_html=True)
    score_fig = render_anomaly_score_chart(anomaly_df, threshold=threshold)
    st.plotly_chart(score_fig, use_container_width=True)

    # ── Section 3: FSM timeline ───────────────────────────────────────────────
    st.markdown("<div class='cp-section'>FSM State Timeline</div>", unsafe_allow_html=True)
    fsm_fig = render_fsm_timeline(anomaly_df)
    st.plotly_chart(fsm_fig, use_container_width=True)

    # ── Section 4: Channel contributions ─────────────────────────────────────
    st.markdown("<div class='cp-section'>Channel Contributions (Latest Window)</div>", unsafe_allow_html=True)
    contrib_fig = render_channel_contributions(anomaly_df)
    st.plotly_chart(contrib_fig, use_container_width=True)

    # ── Recent anomaly table ──────────────────────────────────────────────────
    if anomaly_df is not None and not anomaly_df.empty:
        st.markdown("<div class='cp-section'>Recent Anomaly Scores</div>", unsafe_allow_html=True)
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
        components.html(
            f"""
            <div id="cp-countdown" style="font-size:13px; color:#8892A4; padding:4px 0;"></div>
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
