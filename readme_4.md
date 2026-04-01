# CityPulse Switzerland — Day 4: Grafana Monitoring + Production Hardening

> The MLOps observability layer for CityPulse — real-time pipeline health dashboards, model performance monitoring, alert tracking, and production hardening. This is what separates a demo from a production system.

---

## What Day 4 Builds

Day 1 built the data pipeline. Day 2 built the ML brain. Day 3 built the user dashboard. Day 4 adds the engineering layer that keeps everything running reliably:

- **Grafana Cloud dashboard** — real-time pipeline health: Kafka lag, Airflow DAG success rates, model inference latency, anomaly score trends per city
- **OpenAQ API hardening** — robust air quality fetching with proper error handling, fallback strategies, and data quality checks
- **Model monitoring** — track anomaly score distribution over time, detect model drift, alert when scores look abnormal
- **Pipeline health endpoint** — a `/health` FastAPI endpoint that checks all components (Kafka, Supabase, Redis, HF Space) and returns system status
- **GitHub Actions CI** — automated test run on every push, ensures pipeline never breaks silently

---

## Architecture Added in Day 4

```
Everything from Days 1–3
        +
        ▼
┌─────────────────────────────────────────────────┐
│              OBSERVABILITY LAYER                 │
│                                                 │
│  Grafana Cloud                                  │
│  ├── Pipeline health dashboard                  │
│  ├── Anomaly score trends (8 cities)            │
│  ├── Airflow DAG run history                    │
│  ├── Supabase row counts over time              │
│  └── HF Space inference latency                 │
│                                                 │
│  Model Monitor                                  │
│  ├── Score distribution per city                │
│  ├── Drift detection (PSI per channel)          │
│  └── Alert if score always 0 or always max      │
│                                                 │
│  Health Endpoint                                │
│  └── GET /health → checks all 5 components      │
│                                                 │
│  GitHub Actions CI                              │
│  └── pytest on every push to master             │
└─────────────────────────────────────────────────┘
```

---

## Grafana Cloud Dashboard

### Setup (free forever, no card needed)

1. Go to **grafana.com** → Create free account
2. Create a new stack → choose free tier
3. Go to **Connections → Add data source → PostgreSQL**
4. Connect to Supabase using the DB URL:
   ```
   Host: db.mgawmfmhyfohkfjkrfft.supabase.co:5432
   Database: postgres
   User: postgres
   Password: your_db_password
   SSL mode: require
   ```

### Dashboard Panels

**Panel 1 — Sensor readings per city (last 24hrs)**
```sql
SELECT city, COUNT(*) as readings
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY city
ORDER BY readings DESC
```

**Panel 2 — Anomaly score trend per city**
```sql
SELECT timestamp, city, anomaly_score, visit_score
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp ASC
```

**Panel 3 — FSM state distribution**
```sql
SELECT fsm_state, COUNT(*) as count
FROM anomaly_scores
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY fsm_state
```

**Panel 4 — Alert events log**
```sql
SELECT timestamp, city, from_state, to_state, anomaly_score
FROM alert_events
ORDER BY timestamp DESC
LIMIT 50
```

**Panel 5 — Pipeline health (row count over time)**
```sql
SELECT
  DATE_TRUNC('hour', created_at) as hour,
  COUNT(*) as rows_inserted
FROM sensor_readings
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour ASC
```

---

## Model Monitor

Detects when the LSTM models are behaving unexpectedly.

### What Gets Monitored

```python
class ModelMonitor:
    def check_score_distribution(city, hours=24):
        # Fetch last 24hr anomaly scores
        # Flag if: mean > 0.8 (model always alerting)
        # Flag if: mean < 0.01 (model never detecting anything)
        # Flag if: std < 0.001 (scores not varying — model stuck)

    def check_channel_contributions(city, hours=24):
        # Detect if one channel always dominates (>80%)
        # This suggests a sensor calibration issue

    def compute_psi(city, channel):
        # Population Stability Index
        # Compare last 7 days vs previous 7 days
        # PSI > 0.2 = significant drift → retrain signal

    def generate_health_report():
        # Returns dict: {city: {status, issues, recommendations}}
```

### Monitor Output Example

```
CityPulse Model Health Report — 2026-03-31
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zurich:     OK    — score mean: 0.142, std: 0.089
Geneva:     OK    — score mean: 0.098, std: 0.071
Lucerne:    WARN  — humidity PSI: 0.23 (drift detected)
Interlaken: OK    — score mean: 0.201, std: 0.112
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation: Retrain Lucerne model with recent data
```

---

## Pipeline Health Endpoint

Add a `/health` endpoint to the HuggingFace Space FastAPI app:

```python
GET /health

Response:
{
  "status": "healthy",
  "timestamp": "2026-03-31T07:00:00Z",
  "components": {
    "models": {"status": "ok", "loaded": 8, "total": 8},
    "supabase": {"status": "ok", "latest_row_age_minutes": 4},
    "redis": {"status": "ok", "cities_cached": 8},
    "kafka": {"status": "ok", "topic": "raw-sensor-data"},
    "inference_latency_ms": 142
  },
  "cities": {
    "Zurich": {"fsm_state": "NORMAL", "visit_score": 78},
    "Geneva": {"fsm_state": "NORMAL", "visit_score": 82},
    ...
  }
}
```

This endpoint is what Grafana pings for uptime monitoring.

---

## GitHub Actions CI

Automated test pipeline that runs on every push to master.

### Workflow File: `.github/workflows/ci.yml`

```yaml
name: CityPulse CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install pytest requests python-dotenv pandas numpy
      - name: Run tests
        run: pytest tests/ -v --tb=short
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          UPSTASH_REDIS_URL: ${{ secrets.UPSTASH_REDIS_URL }}
          UPSTASH_REDIS_TOKEN: ${{ secrets.UPSTASH_REDIS_TOKEN }}
```

### Add GitHub Secrets

Go to **github.com/shradhanjalipradhan/CityPulse → Settings → Secrets and variables → Actions** and add:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_TOKEN`

---

## Production Hardening Tasks

### Task 1 — Fix OpenAQ reliability

The current OpenAQ fetcher returns estimated values when no station found. Improve it:

```python
# Current: returns pm25=5.0, pm10=10.0 as estimates
# New: tries 3 radius sizes (25km, 50km, 100km) before falling back
# New: caches successful station IDs in Redis (TTL 24hrs)
# New: logs data quality flag: "real" vs "estimated" per reading
# New: stores data_quality column in sensor_readings table
```

### Task 2 — Airflow restart script

Create `scripts/restart_airflow.ps1` for Windows:

```powershell
# Run this after every Docker restart to restore full pipeline

Write-Host "Restoring CityPulse pipeline..."

# Restore project files in container
docker exec --user root airflow mkdir -p /opt/airflow/citypulse/models/saved_models
docker exec --user root airflow chown -R airflow:root /opt/airflow/citypulse

# Copy project files
docker cp . airflow:/opt/airflow/citypulse/
docker cp .env airflow:/opt/airflow/citypulse/.env
docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/

# Install dependencies inside container
docker exec airflow pip install confluent-kafka supabase requests python-dotenv pandas numpy

# Enable DAG
docker exec airflow airflow dags unpause citypulse_sensor_pipeline

Write-Host "Pipeline restored. DAG active at localhost:8080"
```

### Task 3 — Data quality column

Add `data_quality` column to Supabase:

```sql
ALTER TABLE sensor_readings 
ADD COLUMN IF NOT EXISTS data_quality VARCHAR(20) DEFAULT 'real';

ALTER TABLE sensor_readings
ADD COLUMN IF NOT EXISTS pm25_source VARCHAR(20) DEFAULT 'real';

ALTER TABLE sensor_readings  
ADD COLUMN IF NOT EXISTS pm10_source VARCHAR(20) DEFAULT 'real';
```

### Task 4 — Streamlit app polish

Final UI improvements before sharing publicly:
- Add footer with LinkedIn + GitHub links
- Add "About this project" expandable section explaining the ML stack
- Add loading spinner during data fetch
- Add error state when Redis/Supabase is unreachable
- Default city: Zurich (the startup's target pilot city)
- Add "Last pipeline run" timestamp in sidebar

---

## Day 4 Project Structure

```
citypulse-switzerland/
├── monitoring/
│   ├── model_monitor.py           # PSI drift detection + health report
│   ├── grafana_queries.sql        # All Grafana panel SQL queries
│   └── health_check.py            # Checks all 5 components
├── scripts/
│   ├── restart_airflow.ps1        # Windows: restore pipeline after restart
│   └── setup_grafana.md           # Step-by-step Grafana setup guide
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions test pipeline
└── ... (Days 1–3 files unchanged)
```

---

## Pre-Flight Checklist Before Day 4

- [ ] Day 3 Streamlit app deployed and accessible at public URL
- [ ] GitHub repo is Public
- [ ] Grafana Cloud account created at grafana.com (free)
- [ ] Supabase DB password saved — needed for Grafana connection
- [ ] GitHub Actions enabled on repo (default: yes)
- [ ] At least 50 rows in anomaly_scores table (run a few pipeline cycles)

---

## Quickstart

```bash
# Run model monitor
python monitoring/model_monitor.py

# Check pipeline health
python monitoring/health_check.py

# Run full test suite
pytest tests/ -v

# Restore pipeline after Docker restart (Windows)
.\scripts\restart_airflow.ps1
```

---

## What the Interview Demo Adds After Day 4

With Day 4 complete, your demo has a professional MLOps story:

1. **Show Streamlit app** — live visit scores and anomaly alerts
2. **Show Grafana dashboard** — "This is how I monitor the pipeline in production — Kafka lag, DAG run times, anomaly score trends per city"
3. **Show GitHub Actions** — "Every push runs automated tests — the pipeline never breaks silently"
4. **Show health endpoint** — curl the `/health` URL and show all components green
5. **Show model monitor output** — "I track PSI drift per channel — if Lucerne's humidity distribution shifts, I get a retrain signal automatically"

This is the complete picture of a production ML system, not just a model.

---

## Resume Bullet After Day 4

```
"Built and deployed CityPulse Switzerland — a production-grade 
real-time anomaly detection platform for 8 Swiss cities. Full stack: 
Kafka (Redpanda) for IoT-style sensor ingestion, Airflow for pipeline 
orchestration, LSTM Autoencoder models hosted on HuggingFace Spaces 
for inference, Supabase + Redis for hot/cold storage, Grafana Cloud 
for MLOps monitoring, and Streamlit Cloud for the user-facing dashboard. 
GitHub Actions CI on every push. Live at [URL]."
```

---

## Companion Projects

- **Project 1**: [LSTM-Autoencoder](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector) — F1=0.814, foundation model
- **Project 2**: [GNN Localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer) — GraphSAGE pipe network fault localization
- **Project 3**: [CityPulse Switzerland](https://github.com/shradhanjalipradhan/CityPulse) — This repo, full production stack

---

*Day 1: Data pipeline — Kafka + Airflow + Supabase + Redis*
*Day 2: ML layer — LSTM models + HuggingFace Spaces + Alert Engine*
*Day 3: Dashboard — Streamlit Cloud + Smart Visit Scorer + Anomaly Alert*
*Day 4: MLOps — Grafana + Model Monitor + CI/CD + Production Hardening (this file)*