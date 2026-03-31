"""
fsm_timeline.py — FSM state timeline and channel contributions charts.
Dark theme with vivid FSM state colours.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

DARK_BG   = "#0A0E1A"
DARK_CARD = "#141B2D"
DARK_GRID = "#1E2740"

FSM_COLORS = {
    "NORMAL":     "#00FF88",
    "SUSPICIOUS": "#FFB800",
    "ALERT":      "#FF6B35",
    "CONFIRMED":  "#FF3366",
}

CONTRIBUTION_COLS = {
    "temp_contribution":     "Temperature",
    "humidity_contribution": "Humidity",
    "wind_contribution":     "Wind Speed",
    "precip_contribution":   "Precipitation",
    "pm25_contribution":     "PM2.5",
    "pm10_contribution":     "PM10",
}

_DARK_LAYOUT = dict(
    paper_bgcolor=DARK_BG,
    plot_bgcolor=DARK_CARD,
    font=dict(color="#E8EAF0"),
)


def render_fsm_timeline(anomaly_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders a stacked horizontal bar showing FSM state distribution."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty or "fsm_state" not in anomaly_df.columns:
        fig.add_annotation(
            text="No FSM state data available.",
            showarrow=False, font=dict(size=13, color="#8892A4"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=120, **_DARK_LAYOUT)
        return fig

    counts = anomaly_df["fsm_state"].value_counts()
    total = counts.sum()

    for state in ["NORMAL", "SUSPICIOUS", "ALERT", "CONFIRMED"]:
        if state in counts:
            pct = round(counts[state] / total * 100, 1)
            fig.add_trace(go.Bar(
                x=[counts[state]],
                y=["FSM State"],
                orientation="h",
                name=f"{state} ({pct}%)",
                marker_color=FSM_COLORS[state],
                hovertemplate=f"<b>{state}</b>: {counts[state]} windows ({pct}%)<extra></extra>",
            ))

    fig.update_layout(
        title=dict(
            text="FSM State Distribution — Last 24 Hours",
            font=dict(color="#00D4FF", size=15),
        ),
        barmode="stack",
        height=130,
        margin=dict(t=40, b=10, l=10, r=10),
        xaxis=dict(showticklabels=False, showgrid=False, linecolor=DARK_GRID),
        yaxis=dict(showticklabels=False, linecolor=DARK_GRID),
        legend=dict(
            orientation="h", y=-0.5, x=0,
            font=dict(color="#E8EAF0"), bgcolor="rgba(0,0,0,0)",
        ),
        **_DARK_LAYOUT,
    )
    return fig


def render_channel_contributions(anomaly_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders a horizontal bar chart of per-channel anomaly contributions."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty:
        fig.add_annotation(
            text="No contribution data available.",
            showarrow=False, font=dict(size=13, color="#8892A4"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=250, **_DARK_LAYOUT)
        return fig

    # Use the latest row
    latest = anomaly_df.sort_values("timestamp").iloc[-1]

    labels, values = [], []
    for col, label in CONTRIBUTION_COLS.items():
        if col in latest and latest[col] is not None:
            labels.append(label)
            values.append(float(latest[col]))

    if not values:
        fig.add_annotation(
            text="Contribution data not yet available.",
            showarrow=False, font=dict(size=13, color="#8892A4"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=250, **_DARK_LAYOUT)
        return fig

    total = sum(values) or 1.0
    pcts = [v / total * 100 for v in values]

    # Sort descending
    pairs = sorted(zip(labels, pcts), key=lambda x: x[1], reverse=True)
    labels_sorted = [p[0] for p in pairs]
    pcts_sorted   = [p[1] for p in pairs]

    # Cyan-to-blue gradient for dark theme
    bar_colors = ["#00D4FF", "#00B8D9", "#0099B3", "#007A8C", "#005C66", "#003D40"]

    fig.add_trace(go.Bar(
        x=pcts_sorted,
        y=labels_sorted,
        orientation="h",
        marker_color=bar_colors[:len(labels_sorted)],
        text=[f"{p:.1f}%" for p in pcts_sorted],
        textposition="outside",
        textfont=dict(color="#E8EAF0"),
        hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="Channel Contributions (Latest Window)",
            font=dict(color="#00D4FF", size=15),
        ),
        xaxis_title="% of Anomaly Score",
        height=280,
        margin=dict(t=50, b=30, l=120, r=70),
        hoverlabel=dict(bgcolor="#141B2D", font_color="#E8EAF0"),
        **_DARK_LAYOUT,
    )
    fig.update_xaxes(
        range=[0, max(pcts_sorted) * 1.35],
        showgrid=True,
        gridcolor=DARK_GRID,
        tickfont=dict(color="#8892A4"),
    )
    fig.update_yaxes(tickfont=dict(color="#E8EAF0"))
    return fig
