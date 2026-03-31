"""
gauge_chart.py — Plotly Indicator gauge for the Visit Score (0-100).
Dark theme with gradient steps and glowing needle.
"""

import plotly.graph_objects as go


def score_color(score: int) -> str:
    if score >= 80:
        return "#00FF88"
    elif score >= 60:
        return "#FFB800"
    elif score >= 40:
        return "#FF6B35"
    return "#FF3366"


def score_label(score: int) -> str:
    if score >= 80:
        return "Great time to visit"
    elif score >= 60:
        return "Good — minor caution"
    elif score >= 40:
        return "Consider alternatives"
    return "Not recommended today"


def render_gauge(score: int, city: str) -> go.Figure:
    """Renders a dark-themed 0-100 visit score gauge."""
    color = score_color(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={
            "text": f"{city.upper()} VISIT SCORE",
            "font": {"size": 18, "color": "#E8EAF0"},
        },
        number={"font": {"size": 72, "color": color}, "suffix": ""},
        gauge={
            "axis": {
                "range": [0, 100],
                "tickwidth": 1,
                "tickcolor": "#2A3550",
                "tickfont": {"color": "#8892A4"},
            },
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": "#141B2D",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  39], "color": "#3D0A1A"},
                {"range": [40, 59], "color": "#2D1500"},
                {"range": [60, 79], "color": "#2D2200"},
                {"range": [80, 100], "color": "#003D1A"},
            ],
            "threshold": {
                "line": {"color": color, "width": 5},
                "thickness": 0.80,
                "value": score,
            },
        },
    ))
    fig.update_layout(
        height=300,
        margin=dict(t=70, b=10, l=30, r=30),
        paper_bgcolor="#0A0E1A",
        font={"color": "#E8EAF0"},
    )
    return fig
