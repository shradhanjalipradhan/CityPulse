-- ============================================================
-- CityPulse Switzerland — Grafana Dashboard SQL Queries
-- Data source: Supabase PostgreSQL
-- Host: db.mgawmfmhyfohkfjkrfft.supabase.co:5432
-- ============================================================

-- ── Panel 1: Sensor readings per city (last 24 hrs) ─────────
-- Visualization: Bar chart  |  Refresh: 5 min
SELECT
    city,
    COUNT(*) AS readings
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY city
ORDER BY readings DESC;


-- ── Panel 2: Anomaly score trend per city (time series) ─────
-- Visualization: Time series  |  Refresh: 5 min
SELECT
    timestamp,
    city,
    anomaly_score,
    visit_score
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp ASC;


-- ── Panel 3: FSM state distribution (last 24 hrs) ───────────
-- Visualization: Pie chart / Bar gauge  |  Refresh: 5 min
SELECT
    fsm_state,
    COUNT(*) AS count
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY fsm_state
ORDER BY count DESC;


-- ── Panel 4: Alert events log (latest 50) ───────────────────
-- Visualization: Table  |  Refresh: 5 min
SELECT
    timestamp,
    city,
    from_state,
    to_state,
    anomaly_score
FROM alert_events
ORDER BY timestamp DESC
LIMIT 50;


-- ── Panel 5: Pipeline throughput — rows per hour (7 days) ───
-- Visualization: Time series (area)  |  Refresh: 1 hr
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    COUNT(*) AS rows_inserted
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour ASC;


-- ── Panel 6: Visit score per city (latest value) ────────────
-- Visualization: Stat / Gauge  |  Refresh: 5 min
SELECT DISTINCT ON (city)
    city,
    visit_score,
    fsm_state,
    timestamp
FROM anomaly_scores
ORDER BY city, timestamp DESC;


-- ── Panel 7: Average anomaly score per city (last 24 hrs) ───
-- Visualization: Bar chart  |  Refresh: 5 min
SELECT
    city,
    ROUND(AVG(anomaly_score)::numeric, 4) AS avg_score,
    ROUND(STDDEV(anomaly_score)::numeric, 4) AS std_score,
    COUNT(*) AS window_count
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY city
ORDER BY avg_score DESC;


-- ── Panel 8: Hourly anomaly window count per city ───────────
-- Visualization: Heatmap  |  Refresh: 1 hr
SELECT
    DATE_TRUNC('hour', timestamp) AS hour,
    city,
    COUNT(*) AS windows
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '48 hours'
  AND fsm_state IN ('ALERT', 'CONFIRMED')
GROUP BY hour, city
ORDER BY hour ASC, city;


-- ── Panel 9: Data quality — estimated vs real PM readings ───
-- Visualization: Pie / Bar  |  Refresh: 1 hr
SELECT
    COALESCE(pm25_source, 'real') AS pm25_source,
    COUNT(*) AS count
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY pm25_source;


-- ── Panel 10: Sensor reading freshness (latest per city) ────
-- Visualization: Table  |  Refresh: 1 min
SELECT DISTINCT ON (city)
    city,
    timestamp,
    ROUND(EXTRACT(EPOCH FROM (NOW() - timestamp)) / 60) AS age_minutes,
    temperature_c,
    humidity_pct
FROM sensor_readings
ORDER BY city, timestamp DESC;
