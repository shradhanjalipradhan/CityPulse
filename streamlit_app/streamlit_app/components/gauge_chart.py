"""
gauge_chart.py — Plotly Indicator gauge for the Visit Score (0-100).
Color-coded green / amber / orange / red by score range.
"""

import plotly.graph_objects as go


def score_color(score: int) -> str:
    if score >= 80:
        return "#2ECC71"
    elif score >= 60:
        return "#F39C12"
    elif score >= 40:
        return "#E67E22"
    return "#E74C3C"


def score_label(score: int) -> str:
    if score >= 80:
        return "Great time to visit"
    elif score >= 60:
        return "Good — minor caution"
    elif score >= 40:
        return "Consider alternatives"
    return "Not recommended today"


def render_gauge(score: int, city: str) -> go.Figure:
    """Renders a 0-100 visit score gauge for a city."""
    color = score_color(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": f"{city.upper()} VISIT SCORE", "font": {"size": 18, "color": "#262730"}},
        number={"font": {"size": 64, "color": color}, "suffix": ""},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#888"},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "borderwidth": 2,
            "bordercolor": "#E0E0E0",
            "steps": [
                {"range": [0,  39], "color": "#FADBD8"},
                {"range": [40, 59], "color": "#FAE5D3"},
                {"range": [60, 79], "color": "#FDEBD0"},
                {"range": [80, 100], "color": "#D5F5E3"},
            ],
            "threshold": {
                "line": {"color": color, "width": 4},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig.update_layout(
        height=280,
        margin=dict(t=60, b=10, l=30, r=30),
        paper_bgcolor="white",
    )
    return fig
