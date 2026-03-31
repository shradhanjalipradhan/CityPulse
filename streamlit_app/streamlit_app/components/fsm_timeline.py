"""
fsm_timeline.py — FSM state timeline and channel contributions charts.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go


FSM_COLORS = {
    "NORMAL":    "#2ECC71",
    "SUSPICIOUS":"#F39C12",
    "ALERT":     "#E67E22",
    "CONFIRMED": "#E74C3C",
}

CONTRIBUTION_COLS = {
    "temp_contribution":     "Temperature",
    "humidity_contribution": "Humidity",
    "wind_contribution":     "Wind Speed",
    "precip_contribution":   "Precipitation",
    "pm25_contribution":     "PM2.5",
    "pm10_contribution":     "PM10",
}


def render_fsm_timeline(anomaly_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders a stacked horizontal bar showing FSM state distribution."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty or "fsm_state" not in anomaly_df.columns:
        fig.add_annotation(
            text="No FSM state data available.",
            showarrow=False, font=dict(size=13, color="#888"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=120)
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
        title="FSM State Distribution — Last 24 Hours",
        barmode="stack",
        height=130,
        margin=dict(t=40, b=10, l=10, r=10),
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(showticklabels=False),
        legend=dict(orientation="h", y=-0.3, x=0),
        paper_bgcolor="white",
    )
    return fig


def render_channel_contributions(anomaly_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders a horizontal bar chart of per-channel anomaly contributions."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty:
        fig.add_annotation(
            text="No contribution data available.",
            showarrow=False, font=dict(size=13, color="#888"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=250)
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
            showarrow=False, font=dict(size=13, color="#888"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=250)
        return fig

    total = sum(values) or 1.0
    pcts = [v / total * 100 for v in values]

    # Sort descending
    pairs = sorted(zip(labels, pcts), key=lambda x: x[1], reverse=True)
    labels_sorted = [p[0] for p in pairs]
    pcts_sorted  = [p[1] for p in pairs]

    bar_colors = ["#1F4E79", "#2874A6", "#2E86C1", "#3498DB", "#5DADE2", "#85C1E9"]

    fig.add_trace(go.Bar(
        x=pcts_sorted,
        y=labels_sorted,
        orientation="h",
        marker_color=bar_colors[:len(labels_sorted)],
        text=[f"{p:.1f}%" for p in pcts_sorted],
        textposition="outside",
        hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        title="Channel Contributions (Latest Window)",
        xaxis_title="% of Anomaly Score",
        height=280,
        margin=dict(t=50, b=30, l=120, r=60),
        paper_bgcolor="white",
        plot_bgcolor="#FAFAFA",
    )
    fig.update_xaxes(range=[0, max(pcts_sorted) * 1.3], showgrid=True, gridcolor="#EEEEEE")
    return fig
