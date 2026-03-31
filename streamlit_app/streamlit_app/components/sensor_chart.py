"""
sensor_chart.py — 6-channel sensor time series Plotly chart.
One trace per channel, colour-coded, hover tooltips.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go


CHANNEL_COLORS = {
    "temperature_c":    "#E74C3C",
    "humidity_pct":     "#3498DB",
    "wind_speed_kmh":   "#2ECC71",
    "precipitation_mm": "#9B59B6",
    "pm25":             "#F39C12",
    "pm10":             "#E67E22",
}

CHANNEL_LABELS = {
    "temperature_c":    "Temperature (°C)",
    "humidity_pct":     "Humidity (%)",
    "wind_speed_kmh":   "Wind Speed (km/h)",
    "precipitation_mm": "Precipitation (mm)",
    "pm25":             "PM2.5 (μg/m³)",
    "pm10":             "PM10 (μg/m³)",
}


def render_sensor_chart(sensor_df: Optional[pd.DataFrame]) -> go.Figure:
    """Renders 6-channel time series for last 24 hrs."""
    fig = go.Figure()

    if sensor_df is None or sensor_df.empty:
        fig.add_annotation(
            text="No sensor data available for the last 24 hours.",
            showarrow=False,
            font=dict(size=14, color="#888"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=400)
        return fig

    for channel, color in CHANNEL_COLORS.items():
        if channel not in sensor_df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=sensor_df["timestamp"],
            y=sensor_df[channel],
            name=CHANNEL_LABELS.get(channel, channel),
            line=dict(color=color, width=1.8),
            hovertemplate=(
                f"<b>{CHANNEL_LABELS.get(channel, channel)}</b><br>"
                "%{y:.2f}<br>%{x|%H:%M}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="6-Channel Sensor Time Series — Last 24 Hours",
        xaxis_title="Time (UTC)",
        yaxis_title="Sensor Value",
        legend=dict(orientation="h", y=-0.25, x=0),
        height=420,
        margin=dict(t=50, b=90, l=60, r=20),
        hovermode="x unified",
        paper_bgcolor="white",
        plot_bgcolor="#FAFAFA",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE")
    return fig


def render_anomaly_score_chart(
    anomaly_df: Optional[pd.DataFrame],
    threshold: Optional[float] = None,
) -> go.Figure:
    """Renders anomaly score over time with threshold line."""
    fig = go.Figure()

    if anomaly_df is None or anomaly_df.empty or "anomaly_score" not in anomaly_df.columns:
        fig.add_annotation(
            text="No anomaly score data available.",
            showarrow=False,
            font=dict(size=14, color="#888"),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        fig.update_layout(height=250)
        return fig

    df = anomaly_df.copy()
    ts = df["timestamp"]
    scores = df["anomaly_score"]

    # Shade above threshold (red) and below (green)
    if threshold is not None:
        # Fill below threshold — green
        fig.add_trace(go.Scatter(
            x=ts, y=scores.clip(upper=threshold),
            fill="tozeroy",
            fillcolor="rgba(46,204,113,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Fill above threshold — red
        above = scores.copy()
        above[above <= threshold] = threshold
        fig.add_trace(go.Scatter(
            x=ts, y=above,
            fill="tozeroy",
            fillcolor="rgba(231,76,60,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Threshold line
        fig.add_hline(
            y=threshold,
            line_dash="dash",
            line_color="#E74C3C",
            annotation_text=f"threshold ({threshold:.3f})",
            annotation_position="top right",
        )

    # Anomaly score line
    fig.add_trace(go.Scatter(
        x=ts, y=scores,
        name="Anomaly Score",
        line=dict(color="#1F4E79", width=2),
        hovertemplate="<b>Score</b>: %{y:.4f}<br>%{x|%H:%M}<extra></extra>",
    ))

    fig.update_layout(
        title="Anomaly Score — Last 24 Hours",
        xaxis_title="Time (UTC)",
        yaxis_title="Reconstruction Error",
        height=280,
        margin=dict(t=50, b=50, l=60, r=20),
        paper_bgcolor="white",
        plot_bgcolor="#FAFAFA",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE")
    return fig
