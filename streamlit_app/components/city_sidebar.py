"""
city_sidebar.py — Sidebar city selector and all-cities comparison table.
Uses st.session_state to persist the selected city across page navigations.
Dark theme with vivid HTML colour dots for FSM states.
"""

from typing import Dict, List, Optional

import streamlit as st

CITY_NAMES: List[str] = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]

# Emoji dots kept for backward-compat imports in other modules
FSM_DOT = {
    "NORMAL":    "🟢",
    "SUSPICIOUS":"🟡",
    "ALERT":     "🟠",
    "CONFIRMED": "🔴",
}

# Vivid HTML coloured dots for dark sidebar
_FSM_HTML_DOT = {
    "NORMAL":    "<span style='color:#00FF88;font-size:14px;'>●</span>",
    "SUSPICIOUS":"<span style='color:#FFB800;font-size:14px;'>●</span>",
    "ALERT":     "<span style='color:#FF6B35;font-size:14px;'>●</span>",
    "CONFIRMED": "<span style='color:#FF3366;font-size:14px;'>●</span>",
}

_FSM_SCORE_COLOR = {
    "NORMAL":    "#00FF88",
    "SUSPICIOUS":"#FFB800",
    "ALERT":     "#FF6B35",
    "CONFIRMED": "#FF3366",
}


def render_sidebar(all_states: Dict[str, Optional[Dict]]) -> str:
    """Renders the sidebar with city selector and all-cities comparison.

    Args:
        all_states: Dict of city → state dict from redis_reader.

    Returns:
        The currently selected city name.
    """
    with st.sidebar:
        st.image(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f3/Flag_of_Switzerland.svg/240px-Flag_of_Switzerland.svg.png",
            width=40,
        )
        st.markdown(
            "<h2 style='color:#00D4FF;margin:4px 0 2px;'>CityPulse</h2>"
            "<p style='color:#8892A4;margin:0 0 8px;font-size:13px;'>Switzerland</p>",
            unsafe_allow_html=True,
        )
        st.caption("Real-time urban anomaly monitor")
        st.divider()

        # City selector
        if "selected_city" not in st.session_state:
            st.session_state.selected_city = "Zurich"

        selected = st.selectbox(
            "Select City",
            options=CITY_NAMES,
            index=CITY_NAMES.index(st.session_state.selected_city),
            key="city_selector",
        )
        st.session_state.selected_city = selected

        st.divider()
        st.markdown(
            "<p style='color:#8892A4;font-size:12px;font-weight:600;"
            "letter-spacing:1px;margin-bottom:6px;'>ALL CITIES</p>",
            unsafe_allow_html=True,
        )

        # All-cities comparison table
        for city in CITY_NAMES:
            state = all_states.get(city)
            if state:
                score   = state.get("visit_score", "—")
                fsm     = state.get("fsm_state", "NORMAL")
                dot     = _FSM_HTML_DOT.get(fsm, "<span style='color:#8892A4;'>●</span>")
                sc_color = _FSM_SCORE_COLOR.get(fsm, "#8892A4")
                score_str = str(score) if score is not None else "—"
            else:
                dot       = "<span style='color:#8892A4;'>●</span>"
                sc_color  = "#8892A4"
                score_str = "—"

            # Bold + cyan name for selected city
            if city == selected:
                city_html = f"<b style='color:#00D4FF;'>{city}</b>"
            else:
                city_html = f"<span style='color:#E8EAF0;'>{city}</span>"

            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;padding:2px 0;'>"
                f"  <span>{dot}&nbsp;{city_html}</span>"
                f"  <code style='color:{sc_color};font-size:12px;'>{score_str}</code>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown(
            "<div style='font-size:11px;color:#8892A4;line-height:1.8;'>"
            "<span style='color:#00FF88;'>●</span> NORMAL &nbsp;"
            "<span style='color:#FFB800;'>●</span> SUSPICIOUS<br>"
            "<span style='color:#FF6B35;'>●</span> ALERT &nbsp;&nbsp;"
            "<span style='color:#FF3366;'>●</span> CONFIRMED"
            "</div>",
            unsafe_allow_html=True,
        )

    return selected
