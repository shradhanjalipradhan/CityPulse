"""
city_sidebar.py — Sidebar city selector and all-cities comparison table.
Uses st.session_state to persist the selected city across page navigations.
"""

from typing import Dict, List, Optional

import streamlit as st

CITY_NAMES: List[str] = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]

FSM_DOT = {
    "NORMAL":    "🟢",
    "SUSPICIOUS":"🟡",
    "ALERT":     "🟠",
    "CONFIRMED": "🔴",
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
        st.title("CityPulse Switzerland")
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
        st.subheader("All Cities")

        # All-cities comparison table
        for city in CITY_NAMES:
            state = all_states.get(city)
            if state:
                score = state.get("visit_score", "—")
                fsm   = state.get("fsm_state", "NORMAL")
                dot   = FSM_DOT.get(fsm, "⚪")
                score_str = str(score) if score is not None else "—"
            else:
                dot, score_str = "⚪", "—"

            # Highlight selected city
            prefix = "**" if city == selected else ""
            suffix = "**" if city == selected else ""
            st.markdown(
                f"{dot} {prefix}{city}{suffix} &nbsp;&nbsp; `{score_str}`",
                unsafe_allow_html=True,
            )

        st.divider()
        st.caption("🟢 NORMAL  🟡 SUSPICIOUS")
        st.caption("🟠 ALERT   🔴 CONFIRMED")

    return selected
