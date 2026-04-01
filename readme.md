# CityPulse Switzerland

> Real-time urban intelligence platform for Switzerland — combining multivariate LSTM anomaly detection, live weather and air quality monitoring, and smart visit recommendations across 8 Swiss cities. Built on a full production-grade data engineering and MLOps stack.

[![Streamlit App](https://img.shields.io/badge/Live_App-Streamlit_Cloud-FF4B4B?style=for-the-badge&logo=streamlit)](https://citypulse-byacpgzyklxpxm93gsby47.streamlit.app)
[![HuggingFace](https://img.shields.io/badge/Inference_API-HuggingFace_Spaces-FFD21E?style=for-the-badge&logo=huggingface)](https://huggingface.co/spaces/shradhanjalipradhan/citypulse-inference)
[![GitHub](https://img.shields.io/badge/Code-GitHub-181717?style=for-the-badge&logo=github)](https://github.com/shradhanjalipradhan/CityPulse)
[![CI](https://img.shields.io/github/actions/workflow/status/shradhanjalipradhan/CityPulse/ci.yml?style=for-the-badge&label=CI)](https://github.com/shradhanjalipradhan/CityPulse/actions)
![System Architecture](https://raw.githubusercontent.com/shradhanjalipradhan/CityPulse/master/Real-Time%20Air%20Quality-2026-04-01-041645.png)

---

## Live Demo

| Component | URL | Status |
|-----------|-----|--------|
| Streamlit Dashboard | [citypulse-byacpgzyklxpxm93gsby47.streamlit.app](https://citypulse-byacpgzyklxpxm93gsby47.streamlit.app) | Live |
| HuggingFace Inference API | [shradhanjalipradhan/citypulse-inference](https://huggingface.co/spaces/shradhanjalipradhan/citypulse-inference) | Live |
| GitHub Repo | [shradhanjalipradhan/CityPulse](https://github.com/shradhanjalipradhan/CityPulse) | Public |

---

## What Is CityPulse?

CityPulse Switzerland answers one question for tourists and locals: **should I visit this Swiss city today?**

It continuously ingests live weather and air quality sensor data from 8 Swiss cities, runs an LSTM Autoencoder anomaly detection model on each city's data stream every 5 minutes, and surfaces a **Smart Visit Score (0–100)** alongside real-time anomaly alerts — all powered by a production-grade data engineering stack running entirely on free-tier cloud infrastructure.

The core insight: detecting weather and air quality anomalies in a city is the same computational problem as detecting water leaks in a building pipe network. The same LSTM Autoencoder architecture, the same finite state machine alert engine, the same pipeline pattern — applied to a different sensor domain.

---

## The 8 Swiss Cities

| City | Altitude | Key characteristic |
|------|----------|-------------------|
| Zurich | 408m | Financial hub, highest sensor density |
| Geneva | 375m | Lake Geneva microclimate, most stable baseline |
| Bern | 542m | Alpine weather patterns, capital city |
| Lucerne | 435m | Lake valley variability, highest anomaly threshold |
| Basel | 260m | Rhine valley, industrial air quality signals |
| Interlaken | 570m | Alpine valley, extreme weather events |
| Lausanne | 447m | Lake Geneva, stable baseline similar to Geneva |
| Zermatt | 1608m | High altitude, unique sensor profile, lowest AQ pollution |

---

## Full System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA INGESTION (every 5 min)                  │
│                                                                   │
│  OpenMeteo API          OpenAQ API (with API key)               │
│  (weather — free)       (air quality — free)                     │
│       │                       │                                   │
│       └──────────┬────────────┘                                   │
│                  ▼                                                │
│           Airflow DAG                                             │
│        (citypulse_sensor_pipeline)                               │
│                  │                                                │
│                  ▼                                                │
│         Kafka Producer                                            │
│    (Redpanda Cloud — eu-west-2)                                  │
│    Topic: raw-sensor-data                                         │
└─────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  STREAM PROCESSING                                │
│                                                                   │
│         Kafka Consumer reads raw-sensor-data                     │
│                   │                                               │
│                   ▼                                               │
│         HuggingFace Spaces                                       │
│         FastAPI — POST /predict                                   │
│         LSTM Autoencoder (6 channels, 8 city models)            │
│                   │                                               │
│         Returns: anomaly_score, fsm_state,                       │
│                  visit_score, channel_contributions              │
│                   │                                               │
│         Alert Engine FSM                                          │
│    NORMAL → SUSPICIOUS → ALERT → CONFIRMED                       │
└─────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                     STORAGE                                       │
│                                                                   │
│  Supabase (PostgreSQL)         Redis (Upstash)                   │
│  ├── sensor_readings           ├── city:{name}:latest_reading    │
│  ├── anomaly_scores            ├── city:{name}:fsm_state         │
│  └── alert_events              └── city:{name}:visit_score       │
│                                                                   │
│  Cold storage — full history   Hot cache — sub-10ms reads        │
│  Realtime subscriptions        TTL: 600 seconds                  │
└─────────────────────────────────────────────────────────────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
┌──────────────────┐  ┌─────────────────────────────────────────┐
│  GitHub Actions  │  │         STREAMLIT DASHBOARD              │
│  CI on push      │  │                                          │
│  pytest tests    │  │  Page 1: Smart Visit Scorer             │
│                  │  │  ├── Plotly gauge (0-100)               │
│  Grafana Cloud   │  │  ├── 4 live metric cards                │
│  MLOps monitoring│  │  ├── FSM state badge                    │
│  (architecture   │  │  ├── AI reasoning text                  │
│   built, network │  │  └── All-cities sidebar comparison      │
│   restrictions   │  │                                          │
│   on free tier)  │  │  Page 2: Real-Time Anomaly Alert        │
│                  │  │  ├── 6-channel live time-series chart   │
│                  │  │  ├── Anomaly score overlay              │
│                  │  │  ├── FSM state timeline                 │
│                  │  │  └── Channel contribution breakdown     │
└──────────────────┘  └─────────────────────────────────────────┘
```

---

## The ML Core

### LSTM Autoencoder — Why Unsupervised

Weather anomalies in Swiss cities are **rare events with no labeled ground truth**. A supervised classifier requires labeled anomaly examples for training — unavailable at deployment time. The reconstruction-based approach requires only normal operating data to bootstrap, available from day one.

### Architecture

```
Input: (batch, window=50, channels=6)
       temperature_c | humidity_pct | wind_speed_kmh
       precipitation_mm | pm25 | pm10
              │
              ▼
┌─────────────────────────────┐
│  Encoder                    │
│  LSTM layer 1 (hidden=64)   │
│  LSTM layer 2 (hidden=64)   │
│  Dropout (0.2)              │
│  Linear → latent (dim=16)   │
└─────────────────────────────┘
              │ latent vector (dim=16)
              ▼
┌─────────────────────────────┐
│  Decoder                    │
│  Linear → hidden (64)       │
│  LSTM layer 1 (hidden=64)   │
│  LSTM layer 2 (hidden=64)   │
│  Linear → output (6)        │
└─────────────────────────────┘
              │
              ▼
Reconstruction error → anomaly score
Channel contributions → which sensor is anomalous
```

### Training Results

Trained on 30 days of real historical data per city. One model per city — each Swiss city has a unique environmental baseline.

| City | Val Loss | Threshold | Notes |
|------|----------|-----------|-------|
| Zurich | 0.7898 | 1.3532 | Dense urban sensors |
| Geneva | 0.5329 | 0.6289 | Lowest val loss — stable lake microclimate |
| Bern | 0.7510 | 1.0442 | Alpine weather patterns |
| Lucerne | 0.9856 | 1.7964 | Highest threshold — lake valley variability |
| Basel | 0.7525 | 1.2285 | Rhine valley industrial signals |
| Interlaken | 0.7457 | 1.4628 | Alpine extreme weather |
| Lausanne | 0.6082 | 1.2280 | Lake Geneva stable baseline |
| Zermatt | 0.6144 | 1.1882 | High altitude unique profile |

**Key insight**: Geneva and Lausanne have the lowest val loss — their Lake Geneva microclimate is the most predictable. Lucerne has the highest threshold — the lake valley creates natural variability the model correctly learns to tolerate.

### Finite State Machine Alert Engine

```
NORMAL ──[score > threshold, 1 window]──────────► SUSPICIOUS
SUSPICIOUS ──[score > threshold, 3 consecutive]──► ALERT
ALERT ──[score > 1.5× threshold, 5 windows]──────► CONFIRMED
Any state ──[score below threshold, 5 windows]───► NORMAL
```

### Visit Score Formula

```
base = 100 - (normalized_anomaly_score × 40)
penalties: SUSPICIOUS=-10, ALERT=-20, CONFIRMED=-35
bonus: hour 10–16 UTC → +10 (peak visiting hours)
visit_score = clamp(base + bonus - penalty, 0, 100)
```

### HuggingFace Inference API

Live at: `https://shradhanjalipradhan-citypulse-inference.hf.space`

```bash
curl -X POST https://shradhanjalipradhan-citypulse-inference.hf.space/predict \
  -H "Content-Type: application/json" \
  -d '{"city": "Zurich", "window": []}'
```

Response:
```json
{
  "city": "Zurich",
  "anomaly_score": 3.404,
  "fsm_state": "CONFIRMED",
  "visit_score": 0,
  "threshold": 1.353,
  "channel_contributions": {
    "temperature_c": 0.421,
    "humidity_pct": 0.312,
    "wind_speed_kmh": 0.089,
    "precipitation_mm": 0.041,
    "pm25": 0.091,
    "pm10": 0.046
  }
}
```

---

## Airflow Pipeline DAG

4-task pipeline running every 5 minutes:

```
fetch_and_publish → consume_and_store → run_inference → log_pipeline_health
```

| Task | What it does |
|------|-------------|
| `fetch_and_publish` | Fetches OpenMeteo + OpenAQ for 8 cities, publishes to Kafka |
| `consume_and_store` | Consumes Kafka, writes to Supabase + Redis |
| `run_inference` | Calls HF Space, writes anomaly scores + FSM states |
| `log_pipeline_health` | Logs row counts and system status |

---

## Sensor Data

Two real-time free data sources — no API keys required for weather, OpenAQ key for air quality:

| Channel | Source | Normal range | Anomaly signal |
|---------|--------|-------------|----------------|
| `temperature_c` | OpenMeteo | City-specific | Extreme cold/heat |
| `humidity_pct` | OpenMeteo | 40–90% | >95% sustained |
| `wind_speed_kmh` | OpenMeteo | 0–30 km/h | Storm patterns |
| `precipitation_mm` | OpenMeteo | 0–5mm/hr | Heavy rainfall |
| `pm25` | OpenAQ | 0–15 μg/m³ | Air quality events |
| `pm10` | OpenAQ | 0–20 μg/m³ | Dust/pollution |

---

## Technology Stack

| Layer | Tool | Purpose | Cost |
|-------|------|---------|------|
| Stream ingestion | Redpanda Cloud (Kafka-compatible) | Real-time sensor stream | Free 30 days |
| Orchestration | Apache Airflow 2.8 (Docker) | Pipeline scheduling every 5 min | Free |
| Time-series DB | Supabase (PostgreSQL) | Full sensor + anomaly history | Free forever |
| Cache | Redis (Upstash) | Sub-10ms current state reads | Free 10K req/day |
| ML framework | PyTorch 2.4 | LSTM Autoencoder training | Free |
| Model serving | HuggingFace Spaces | FastAPI inference endpoint | Free forever |
| Dashboard | Streamlit Cloud | User-facing web app | Free forever |
| CI/CD | GitHub Actions | Automated test pipeline | Free |
| Monitoring | Grafana Cloud | MLOps dashboard architecture | Free forever |

**Total infrastructure cost: $0**

---

## Project Structure

```
CityPulse/
├── dags/
│   └── sensor_pipeline_dag.py       # Airflow 4-task DAG
├── data/
│   ├── fetch_weather.py             # OpenMeteo client
│   ├── fetch_airquality.py          # OpenAQ client with key
│   └── cities_config.py             # 8 Swiss cities config
├── kafka/
│   ├── producer.py                  # Redpanda SASL_SSL producer
│   └── consumer.py                  # Kafka consumer → Supabase + Redis
├── database/
│   ├── supabase_client.py           # PostgreSQL operations
│   ├── redis_client.py              # Upstash REST cache
│   └── migrations.sql               # 3 table definitions + indexes
├── models/
│   ├── lstm_autoencoder.py          # 6-channel LSTM AE
│   ├── train_models.py              # Train 8 city models
│   ├── inference_engine.py          # Supabase → HF → Supabase
│   ├── alert_engine.py              # FSM state machine
│   └── saved_models/                # 8 × .pt + scaler + threshold
├── huggingface_space/
│   ├── app.py                       # FastAPI inference server
│   ├── Dockerfile                   # HF Spaces Docker config
│   └── requirements.txt
├── streamlit_app/
│   ├── app.py                       # Smart Visit Scorer (home)
│   ├── pages/
│   │   └── 02_Anomaly_Alert.py      # Real-Time Anomaly Alert
│   ├── components/                  # Plotly chart components
│   └── utils/                       # Redis + Supabase readers
├── monitoring/
│   └── health_check.py              # Pipeline health report
├── scripts/
│   └── restart_pipeline.ps1         # Windows: restore after restart
├── tests/
│   ├── test_fetch_weather.py
│   ├── test_kafka_producer.py
│   └── test_supabase_client.py
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI
├── .streamlit/
│   └── config.toml                  # Dark theme configuration
└── requirements.txt
```

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- Docker Desktop
- Git

### Accounts Required (all free)

| Service | URL | What you get |
|---------|-----|-------------|
| Redpanda Cloud | cloud.redpanda.com | Kafka-compatible streaming |
| Supabase | supabase.com | PostgreSQL + Realtime |
| Upstash | upstash.com | Redis REST API |
| HuggingFace | huggingface.co | Model hosting |
| Streamlit Cloud | share.streamlit.io | App deployment |
| GitHub | github.com | CI/CD |

### Environment Variables

Create `.env` in project root:

```env
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
SUPABASE_DB_URL=postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres

# Redis (Upstash)
UPSTASH_REDIS_URL=https://xxxx.upstash.io
UPSTASH_REDIS_TOKEN=your_token

# Kafka (Redpanda)
KAFKA_BOOTSTRAP_SERVERS=xxxx.eu-west-2.mpx.prd.cloud.redpanda.com:9092
KAFKA_API_KEY=citypulse-user
KAFKA_API_SECRET=your_password
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_TOPIC_SENSOR=raw-sensor-data
KAFKA_TOPIC_ANOMALY=anomaly-results

# HuggingFace
HF_TOKEN=hf_xxxx
HF_USERNAME=shradhanjalipradhan
HF_SPACE_NAME=citypulse-inference

# OpenAQ
OPENAQ_API_KEY=your_openaq_key

# App config
CITIES=Zurich,Geneva,Bern,Lucerne,Basel,Interlaken,Lausanne,Zermatt
MODEL_WINDOW_SIZE=50
MODEL_INPUT_DIM=6
ANOMALY_THRESHOLD_PERCENTILE=95
REFRESH_INTERVAL_SECONDS=300
```

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start Airflow in Docker
docker run -d -p 8080:8080 --name airflow \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=False \
  apache/airflow:2.8.0 standalone

# Run database migrations
python database/supabase_client.py --migrate

# Train all 8 models (~15 min on CPU)
python models/train_models.py

# Deploy inference API to HuggingFace
python huggingface_space/deploy.py

# Run Streamlit locally
streamlit run streamlit_app/app.py

# Deploy Airflow DAG
docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
```

### After Docker Restart

```powershell
# Windows — run this script to restore full pipeline
.\scripts\restart_pipeline.ps1
```

---

## Live System Metrics

| Metric | Value |
|--------|-------|
| Sensor readings in Supabase | 500+ rows |
| Anomaly scores computed | 40+ rows |
| Pipeline cadence | Every 5 minutes |
| Inference latency (HF Space) | ~150ms per city |
| Redis cache TTL | 600 seconds |
| Cities monitored | 8 |
| Models deployed | 8 |

---

## CI/CD

GitHub Actions runs on every push to master:

```yaml
# .github/workflows/ci.yml
- Python 3.10
- pytest tests/ -v --tb=short
- Tests: weather fetch, Kafka producer schema, Supabase client
```

Badge: [![CI](https://img.shields.io/github/actions/workflow/status/shradhanjalipradhan/CityPulse/ci.yml)](https://github.com/shradhanjalipradhan/CityPulse/actions)

---

## Companion Projects

This is the third project in a sensor anomaly detection series:

**Project 1 — Foundation model**
[LSTM-Autoencoder-multivariate-sensor-anomaly-detector](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector)
LSTM Autoencoder on synthetic 4-channel building sensor data. **F1=0.814, all 3/3 leak events detected, all escalated to CONFIRMED state.** The architecture CityPulse extends from synthetic to real data.

**Project 2 — Graph localization** *(coming soon)*
[pipe-network-gnn-localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer)
GraphSAGE GNN on a 20-node pipe network topology. Identifies *where* a fault originated, not just *that* one exists. Directly applicable to water leak localization in building infrastructure.

**Project 3 — CityPulse (this repo)**
Full production stack: Kafka + Airflow + Supabase + Redis + HuggingFace + Streamlit. The same pipeline pattern applied to real public IoT sensor data.

---

## The Water Infrastructure Connection

CityPulse is architecturally identical to a building water leak detection system:

| CityPulse | Water leak system |
|-----------|-------------------|
| OpenMeteo + OpenAQ APIs | MQTT IoT sensor streams |
| Redpanda Kafka topic | IoT message broker |
| 6 weather/AQ channels | pressure, flow, temperature, vibration |
| LSTM Autoencoder per city | LSTM Autoencoder per building |
| Visit score (0-100) | Building safety score |
| FSM alert engine | Same FSM, same transitions |
| Supabase anomaly_scores | Building anomaly log |
| Streamlit dashboard | Facilities management dashboard |

The only changes needed to convert CityPulse into a production water leak detector: swap the data source (MQTT broker instead of REST API) and the sensor channels (pipe sensors instead of weather sensors). Every other layer — Kafka ingestion, Airflow orchestration, LSTM architecture, FSM alert engine, Supabase storage, Redis caching, and the dashboard — is reusable as-is.

---

## Future Roadmap

**v1.1 — Restaurant & Festival Integration**
Personalised restaurant recommendations via Claude AI based on user food preferences. Switzerland Tourism events feed for live festivals. Crowd index from time-of-day + event data.

**v1.2 — Enhanced ML**
Temporal GNN layer over the city network for regional anomaly pattern detection. Adaptive thresholding with monthly retraining. Uncertainty quantification via Monte Carlo dropout.

**v1.3 — Production Hardening**
Kubernetes deployment on GKE free tier. Feast feature store. A/B model testing with traffic splitting. dbt for version-controlled data transformations.

**v2.0 — Water Infrastructure Extension**
Apply the identical pipeline to actual building water sensor data via MQTT. Same architecture, different data source.

---

## Author

**Shradhanjali Pradhan**
AI/ML Engineer | MSc Applied Data Analytics, Boston University
[LinkedIn](https://linkedin.com/in/shradhanjalipradhan) | [GitHub](https://github.com/shradhanjalipradhan)

*Part of a sensor anomaly detection research series spanning synthetic building sensors, graph-based fault localization, and real-time urban environmental monitoring.*

---

*Built entirely on free-tier cloud infrastructure. Total cost: $0.*
