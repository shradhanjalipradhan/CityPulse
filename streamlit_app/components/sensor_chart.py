"""
sensor_chart.py — 6-channel sensor time series and anomaly score charts.
Dark theme with vivid per-channel colours.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

DARK_BG     = "#0A0E1A"
DARK_CARD   = "#141B2D"
DARK_GRID   = "#1E2740"

CHANNEL_COLORS = {
    "temperature_c":    "#FF6B6B",
    "humidity_pct":     "#4ECDC4",
    "wind_speed_kmh":   "#45B7D1",
    "precipitation_mm": "#96CEB4",
    "pm25":             "#FFEAA7",
    "pm10":             "#DDA0DD",
}

CHANNEL_LABELS = {
    "temperature_c":    "Temperature (°C)",
    "humidity_pct":     "Humidity (%)",
    "wind_speed_kmh":   "Wind Speed (km/h)",
    "precipitation_mm": "Precipitation (mm)",
    "pm25":             "PM2.5 (μg/m³)",
    "pm10":             "PM10 (μg/m³)",
}

_DARK_LAYOUT = dict(
    paper_bgcolor=DARK_BG,
    plot_bgcolor=DARK_CARD,
    font=dict(color="#E8EAF0"),
    xaxis=dict(
        gridcolor=DARK_GRID, linecolor=DARK_GRID,
        tickfont=dict(color="#8892A4"),
    ),
    yaxis=dict(
        gridcolor=DARK_GRID, linecolor=DARK_GRID,
        tickfont=dict(color="#8892A4"),
    ),
)


def render_sensor_chart(sensor_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders 6-channel time series — last 24 hrs, dark theme."""
    fig = go.Figure()

    if sensor_df is None or sensor_df.empty:
        fig.add_annotation(
            text="No sensor data available for the last 24 hours.",
            showarrow=False, font=dict(size=14, color="#8892A4"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=420, **_DARK_LAYOUT)
        return fig

    for channel, color in CHANNEL_COLORS.items():
        if channel not in sensor_df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=sensor_df["timestamp"],
            y=sensor_df[channel],
            name=CHANNEL_LABELS.get(channel, channel),
            line=dict(color=color, width=2),
            hovertemplate=(
                f"<b>{CHANNEL_LABELS.get(channel, channel)}</b><br>"
                "%{y:.2f}<br>%{x|%H:%M}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text="6-Channel Sensor Time Series — Last 24 Hours",
            font=dict(color="#00D4FF", size=15),
        ),
        xaxis_title="Time (UTC)",
        yaxis_title="Sensor Value",
        legend=dict(
            orientation="h", y=-0.28, x=0,
            font=dict(color="#E8EAF0"), bgcolor="rgba(0,0,0,0)",
        ),
        height=430,
        margin=dict(t=55, b=95, l=65, r=20),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#141B2D", font_color="#E8EAF0"),
        **_DARK_LAYOUT,
    )
    return fig


def render_anomaly_score_chart(
    anomaly_df: Optional[pd.DataFrame],
    threshold: Optional[float] = None,
) -> go.Figure:
    """Renders anomaly score over time — cyan line, red threshold."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty or "anomaly_score" not in anomaly_df.columns:
        fig.add_annotation(
            text="No anomaly score data available.",
            showarrow=False, font=dict(size=14, color="#8892A4"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=260, **_DARK_LAYOUT)
        return fig

    df = anomaly_df.copy()
    ts     = df["timestamp"]
    scores = df["anomaly_score"]

    if threshold is not None:
        # Green fill below threshold
        fig.add_trace(go.Scatter(
            x=ts, y=scores.clip(upper=threshold),
            fill="tozeroy",
            fillcolor="rgba(0,255,136,0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Red fill above threshold
        above = scores.copy()
        above[above <= threshold] = threshold
        fig.add_trace(go.Scatter(
            x=ts, y=above,
            fill="tozeroy",
            fillcolor="rgba(255,51,102,0.12)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Dashed red threshold line
        fig.add_hline(
            y=threshold,
            line_dash="dash",
            line_color="#FF3366",
            line_width=1.5,
            annotation_text=f"  threshold ({threshold:.3f})",
            annotation_font_color="#FF3366",
            annotation_position="top right",
        )

    # Cyan anomaly score line
    fig.add_trace(go.Scatter(
        x=ts, y=scores,
        name="Anomaly Score",
        line=dict(color="#00D4FF", width=2.5),
        hovertemplate="<b>Score</b>: %{y:.4f}<br>%{x|%H:%M}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="Anomaly Score — Last 24 Hours",
            font=dict(color="#00D4FF", size=15),
        ),
        xaxis_title="Time (UTC)",
        yaxis_title="Reconstruction Error",
        height=280,
        margin=dict(t=55, b=50, l=65, r=20),
        showlegend=False,
        hoverlabel=dict(bgcolor="#141B2D", font_color="#E8EAF0"),
        **_DARK_LAYOUT,
    )
    return fig
