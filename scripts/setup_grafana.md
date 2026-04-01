# CityPulse — Grafana Cloud Setup Guide

Step-by-step guide to connect Grafana Cloud to the CityPulse Supabase database and build the monitoring dashboard.

---

## Step 1 — Create a Free Grafana Cloud Account

1. Go to **grafana.com** → click **Create free account**
2. Sign in with GitHub for one-click setup
3. Create a new **stack** — choose the free tier (forever free, no card required)
4. Note your Grafana URL: `https://<your-org>.grafana.net`

---

## Step 2 — Add Supabase as a PostgreSQL Data Source

1. In Grafana, go to **Connections → Add new data source → PostgreSQL**
2. Fill in the connection details:

```
Host:       db.mgawmfmhyfohkfjkrfft.supabase.co:5432
Database:   postgres
User:       postgres
Password:   <your Supabase DB password>
SSL Mode:   require
```

3. Click **Save & test** — you should see "Database Connection OK"

> **Where to find the DB password**: Supabase dashboard → Project Settings → Database → Connection string

---

## Step 3 — Create a New Dashboard

1. Click **+ → New Dashboard → Add visualization**
2. Select your PostgreSQL data source
3. Switch to **SQL mode** (click "Edit SQL" button)

---

## Step 4 — Add Panels

Copy-paste the queries from `monitoring/grafana_queries.sql`. Recommended panel order:

### Panel 1 — Sensor readings per city (Bar chart)
```sql
SELECT city, COUNT(*) as readings
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY city
ORDER BY readings DESC
```

### Panel 2 — Anomaly score trend (Time series)
```sql
SELECT timestamp, city, anomaly_score, visit_score
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp ASC
```
> Set **Format as: Time series**, X-axis: `timestamp`, Y-axis: `anomaly_score`

### Panel 3 — FSM state distribution (Pie chart)
```sql
SELECT fsm_state, COUNT(*) as count
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY fsm_state
```

### Panel 4 — Visit scores per city (Stat panel)
```sql
SELECT DISTINCT ON (city) city, visit_score, fsm_state, timestamp
FROM anomaly_scores
ORDER BY city, timestamp DESC
```

### Panel 5 — Pipeline throughput (Area chart)
```sql
SELECT DATE_TRUNC('hour', created_at) as hour, COUNT(*) as rows_inserted
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour ASC
```

---

## Step 5 — Configure Auto-Refresh

1. In the dashboard top bar, click the refresh dropdown (default: Off)
2. Set to **5 minutes** for real-time monitoring
3. Set the time range to **Last 24 hours**

---

## Step 6 — Set Up Uptime Alerting (Optional)

1. Go to **Alerting → Alert rules → New alert rule**
2. Use this query to alert when no new rows in 30 minutes:
```sql
SELECT COUNT(*) as recent_rows
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '30 minutes'
```
3. Alert condition: `recent_rows < 1`
4. Set notification channel (email, Slack, PagerDuty)

---

## Step 7 — Share the Dashboard

1. Click the share icon → **Snapshot**
2. Set expiry to **Never**
3. Copy the public URL for your portfolio/resume

---

## Dashboard Variables (Optional)

Add a city filter variable:

1. **Dashboard settings → Variables → Add variable**
2. Name: `city`
3. Type: Query
4. Query:
```sql
SELECT DISTINCT city FROM sensor_readings ORDER BY city
```
5. Use `$city` in your panel queries:
```sql
WHERE city = '$city'
```

---

## Useful Grafana Shortcuts

| Action | Shortcut |
|--------|----------|
| Add panel | `a` |
| Save dashboard | `Ctrl+S` |
| Toggle fullscreen | `F` |
| View JSON model | Dashboard settings → JSON Model |
