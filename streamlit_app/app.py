"""
app.py — CityPulse Switzerland Streamlit Dashboard.
Home page: Smart Visit Scorer.
Navigation to Real-Time Anomaly Alert via sidebar.
"""

import sys
from pathlib import Path
from typing import Optional

# Ensure streamlit_app/ is on sys.path so components/utils are importable
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timezone

import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="CityPulse Switzerland",
    page_icon="🏔️",
    initial_sidebar_state="expanded",
)

from components.city_sidebar import render_sidebar, FSM_DOT
from components.gauge_chart import render_gauge, score_label, score_color
from utils.redis_reader import get_all_city_states, get_latest_reading

# ── Dark Theme CSS ─────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Header banner */
.cp-header {
    background: linear-gradient(135deg, #0A0E1A 0%, #141B2D 60%, #0D1525 100%);
    border-left: 4px solid #00D4FF;
    border-radius: 8px;
    padding: 16px 24px 12px;
    margin-bottom: 8px;
}
.cp-header h1 {
    color: #00D4FF;
    margin: 0 0 4px;
    font-size: 28px;
    letter-spacing: 1px;
}
.cp-header p {
    color: #8892A4;
    margin: 0;
    font-size: 13px;
}

/* FSM state badges */
.fsm-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.fsm-NORMAL    { background: rgba(0,255,136,0.12); color:#00FF88; border:1px solid #00FF88;
                  box-shadow: 0 0 8px rgba(0,255,136,0.25); }
.fsm-SUSPICIOUS{ background: rgba(255,184,0,0.12);  color:#FFB800; border:1px solid #FFB800;
                  box-shadow: 0 0 8px rgba(255,184,0,0.25); }
.fsm-ALERT     { background: rgba(255,107,53,0.12); color:#FF6B35; border:1px solid #FF6B35;
                  box-shadow: 0 0 8px rgba(255,107,53,0.25); }
.fsm-CONFIRMED { background: rgba(255,51,102,0.15); color:#FF3366; border:1px solid #FF3366;
                  box-shadow: 0 0 8px rgba(255,51,102,0.30); }

/* AI Reasoning box */
.cp-reasoning {
    background: #141B2D;
    border-left: 3px solid #00D4FF;
    border-radius: 6px;
    padding: 14px 18px;
    color: #E8EAF0;
    font-style: italic;
    font-size: 15px;
    line-height: 1.6;
}

/* Dark metric cards */
[data-testid="stMetric"] {
    background: #141B2D;
    border: 1px solid #1E2740;
    border-radius: 8px;
    padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] { color: #8892A4 !important; font-size: 12px; }
[data-testid="stMetricValue"] { color: #E8EAF0 !important; }
[data-testid="stMetricDelta"] { font-size: 11px; }

/* Section headers */
.cp-section {
    color: #00D4FF;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin: 12px 0 4px;
    padding-bottom: 4px;
    border-bottom: 1px solid #1E2740;
}
</style>
"""


# ── AI Reasoning Generator ────────────────────────────────────────────────────

def _generate_reasoning(
    city: str,
    visit_score: int,
    fsm_state: str,
    temperature: Optional[float],
    humidity: Optional[float],
    wind_speed: Optional[float],
    pm25: Optional[float],
) -> str:
    """Rule-based 2-sentence visit reasoning."""
    temp = temperature or 0.0
    pm   = pm25 or 5.0

    # Sentence 1 — conditions + anomaly state
    if temp <= 0:
        cond = f"Freezing conditions ({temp:.1f}°C) in {city}"
    elif temp < 10:
        cond = f"Cold but clear conditions ({temp:.1f}°C) in {city}"
    elif temp < 20:
        cond = f"Mild temperatures ({temp:.1f}°C) in {city}"
    else:
        cond = f"Warm conditions ({temp:.1f}°C) in {city}"

    if fsm_state == "NORMAL":
        s1 = f"{cond} — all sensors within normal baseline."
    elif fsm_state == "SUSPICIOUS":
        s1 = f"{cond} — one anomalous sensor window detected."
    elif fsm_state == "ALERT":
        s1 = f"{cond} — 3+ consecutive anomalous sensor windows."
    else:
        s1 = f"{cond} — sustained anomaly event currently in progress."

    # Sentence 2 — air quality + recommendation
    if pm < 12:
        aq = "Air quality is excellent"
    elif pm < 35:
        aq = "Air quality is acceptable"
    else:
        aq = "Air quality is poor (elevated particulates)"

    if visit_score >= 80:
        rec = "— a great time to visit."
    elif visit_score >= 60:
        rec = "— a good time to visit with minor caution."
    elif visit_score >= 40:
        rec = "— consider indoor alternatives today."
    else:
        rec = "— outdoor visits are not recommended right now."

    return f"{s1} {aq} {rec}"


# ── Main Page ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Inject dark CSS
    st.markdown(_CSS, unsafe_allow_html=True)

    # Sidebar — always rendered first
    all_states = get_all_city_states()
    city = render_sidebar(all_states)

    # Fetch current state for selected city
    state = all_states.get(city)
    reading = get_latest_reading(city)

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div class='cp-header'>"
        f"<h1>🏔️ CityPulse Switzerland</h1>"
        f"<p>Smart Visit Scorer · Powered by LSTM Autoencoder anomaly detection · "
        f"Updated every 5 minutes via Kafka pipeline</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if state is None:
        st.warning(
            f"No inference data available for {city} yet. "
            "The Airflow pipeline may still be warming up — check back in a few minutes."
        )
        st.stop()

    visit_score   = int(state.get("visit_score") or 0)
    fsm_state     = state.get("fsm_state", "NORMAL")
    anomaly_score = state.get("anomaly_score")
    threshold     = state.get("threshold")
    last_ts       = state.get("timestamp", "")

    # ── Gauge ─────────────────────────────────────────────────────────────────
    col_gauge, col_info = st.columns([1, 1])

    with col_gauge:
        fig = render_gauge(visit_score, city)
        st.plotly_chart(fig, use_container_width=True)
        label = score_label(visit_score)
        color = score_color(visit_score)
        st.markdown(
            f"<p style='text-align:center; font-size:18px; "
            f"color:{color}; font-weight:600;'>{label}</p>",
            unsafe_allow_html=True,
        )

    # ── Sensor Metrics ────────────────────────────────────────────────────────
    with col_info:
        st.markdown("<div class='cp-section'>Current Conditions</div>", unsafe_allow_html=True)

        temp  = reading.get("temperature_c")  if reading else None
        hum   = reading.get("humidity_pct")   if reading else None
        wind  = reading.get("wind_speed_kmh") if reading else None
        pm10  = reading.get("pm10")           if reading else None
        pm25  = reading.get("pm25")           if reading else None

        m1, m2, m3, m4 = st.columns(4)

        with m1:
            if temp is not None:
                label_t = "normal" if -5 < temp < 30 else ("cold" if temp <= -5 else "hot")
                st.metric("Temperature", f"{temp:.1f}°C", label_t)
            else:
                st.metric("Temperature", "—")

        with m2:
            if hum is not None:
                label_h = "high" if hum > 80 else ("low" if hum < 30 else "normal")
                st.metric("Humidity", f"{hum:.0f}%", label_h)
            else:
                st.metric("Humidity", "—")

        with m3:
            if wind is not None:
                label_w = "calm" if wind < 20 else ("moderate" if wind < 40 else "strong")
                st.metric("Wind Speed", f"{wind:.1f} km/h", label_w)
            else:
                st.metric("Wind Speed", "—")

        with m4:
            if pm10 is not None:
                aq_label = "good" if pm10 < 20 else ("moderate" if pm10 < 50 else "poor")
                st.metric("Air Quality", aq_label, f"PM10: {pm10:.1f}")
            else:
                st.metric("Air Quality", "—")

        st.divider()

        # FSM State Badge
        fsm_meaning = {
            "NORMAL":    "All sensors within baseline — no anomalies",
            "SUSPICIOUS":"One anomalous window detected",
            "ALERT":     "3+ consecutive anomalous windows",
            "CONFIRMED": "Sustained anomaly — significant event",
        }
        st.markdown(
            f"<b style='color:#8892A4;'>Anomaly State:</b>&nbsp;"
            f"<span class='fsm-badge fsm-{fsm_state}'>{fsm_state}</span>",
            unsafe_allow_html=True,
        )
        st.caption(fsm_meaning.get(fsm_state, ""))

        if anomaly_score is not None and threshold is not None:
            st.progress(
                min(1.0, anomaly_score / (threshold * 2)),
                text=f"Score: {anomaly_score:.4f}  ·  Threshold: {threshold:.4f}",
            )

    # ── AI Reasoning ──────────────────────────────────────────────────────────
    st.divider()
    reasoning = _generate_reasoning(
        city, visit_score, fsm_state, temp, hum, wind, pm25
    )
    st.markdown("<div class='cp-section'>AI Reasoning</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='cp-reasoning'>\"{reasoning}\"</div>",
        unsafe_allow_html=True,
    )

    # ── Footer ────────────────────────────────────────────────────────────────
    st.divider()
    now = datetime.now(timezone.utc)
    if last_ts:
        try:
            import pandas as pd
            last_dt = pd.to_datetime(last_ts, utc=True)
            delta   = now - last_dt.to_pydatetime()
            mins    = int(delta.total_seconds() // 60)
            age     = f"{mins} minute{'s' if mins != 1 else ''} ago"
        except Exception:
            age = last_ts
    else:
        age = "unknown"

    col_ts, col_btn = st.columns([3, 1])
    with col_ts:
        st.caption(f"Last updated: {age} · Auto-refresh: every 5 min via pipeline")
    with col_btn:
        if st.button("Refresh Now", use_container_width=True):
            st.rerun()


if __name__ == "__main__":
    main()
else:
    main()
