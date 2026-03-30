# CityPulse Switzerland

> Real-time urban intelligence platform for Switzerland — combining multivariate anomaly detection, live weather and air quality monitoring, and smart visit recommendations across 8 Swiss cities.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-red.svg)](https://pytorch.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-FF4B4B.svg)](https://streamlit.io)
[![Kafka](https://img.shields.io/badge/Apache_Kafka-Confluent_Cloud-231F20.svg)](https://confluent.io)
[![Airflow](https://img.shields.io/badge/Apache_Airflow-2.8-017CEE.svg)](https://airflow.apache.org)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E.svg)](https://supabase.com)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Spaces-FFD21E.svg)](https://huggingface.co/spaces)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What Is CityPulse?

CityPulse Switzerland is an end-to-end real-time ML platform that helps tourists and locals make informed decisions about visiting Swiss cities. It continuously ingests live weather and air quality sensor data from 8 Swiss cities, runs an LSTM Autoencoder anomaly detection model on each city's data stream, and surfaces a **Smart Visit Score** (0–100) alongside real-time anomaly alerts.

Under the hood it is a production-grade data engineering and MLOps system: Kafka handles streaming ingestion, Airflow orchestrates the pipeline every 5 minutes, a LSTM model hosted on HuggingFace Spaces runs inference, Supabase stores the time-series history, Redis caches the latest state for sub-10ms reads, and Grafana monitors pipeline health. Streamlit delivers the user-facing dashboard.

This project is a direct extension of [LSTM-Autoencoder-multivariate-sensor-anomaly-detector](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector) — the same model architecture applied to real-time public sensor data with a full production stack around it.

---

## Live Demo

**Streamlit App:** [citypulse-switzerland.streamlit.app](https://citypulse-switzerland.streamlit.app) *(coming soon)*

**HuggingFace Inference API:** [shradhanjalipradhan/citypulse-inference](https://huggingface.co/spaces/shradhanjalipradhan/citypulse-inference) *(coming soon)*

**Grafana Dashboard:** [citypulse.grafana.net](https://citypulse.grafana.net) *(coming soon)*

---

## The 8 Swiss Cities

| City | Lat | Lon | Key feature |
|------|-----|-----|-------------|
| Zurich | 47.3769 | 8.5417 | Financial hub, highest sensor density |
| Geneva | 46.2044 | 6.1432 | International city, lake proximity effects |
| Bern | 46.9481 | 7.4474 | Capital, alpine weather patterns |
| Lucerne | 47.0502 | 8.3093 | Tourist hotspot, Lake Lucerne microclimate |
| Basel | 47.5596 | 7.5886 | Rhine valley, industrial air quality signals |
| Interlaken | 46.6863 | 7.8632 | Alpine valley, extreme weather events |
| Lausanne | 46.5197 | 6.6323 | Lake Geneva, EPFL campus proximity |
| Zermatt | 46.0207 | 7.7491 | High altitude (1,608m), unique sensor profiles |

---

## Current Architecture (v1.0 — in production)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DATA INGESTION LAYER                            │
│                                                                     │
│   OpenMeteo API          OpenAQ API                                 │
│   (weather — free)       (air quality — free)                       │
│        │                      │                                     │
│        └──────────┬───────────┘                                     │
│                   │                                                 │
│            Airflow DAG                                              │
│         (every 5 minutes)                                           │
│                   │                                                 │
│                   ▼                                                 │
│         Kafka Producer                                              │
│    (Confluent Cloud — eu-west-1)                                    │
│         Topic: raw-sensor-data                                      │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     STREAM PROCESSING LAYER                         │
│                                                                     │
│         Kafka Consumer reads raw-sensor-data                        │
│                   │                                                 │
│                   ▼                                                 │
│         HuggingFace Spaces                                          │
│         FastAPI Inference Endpoint                                  │
│         POST /predict                                               │
│         (LSTM Autoencoder — 6 channels — 8 city models)            │
│                   │                                                 │
│         Returns: anomaly_score, fsm_state,                          │
│                  visit_score, channel_contributions                 │
│                   │                                                 │
│         Kafka Producer → Topic: anomaly-results                     │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     STORAGE LAYER                                   │
│                                                                     │
│   Supabase (PostgreSQL)          Redis (Upstash)                    │
│   ├── sensor_readings            ├── city:{name}:latest_reading     │
│   ├── anomaly_scores             ├── city:{name}:fsm_state          │
│   └── alert_events               └── city:{name}:visit_score        │
│                                                                     │
│   Cold storage — full history    Hot cache — sub-10ms reads         │
│   Realtime subscriptions         TTL: 600 seconds                   │
└─────────────────────────────────────────────────────────────────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
┌──────────────────┐  ┌────────────────────────────────────────────┐
│  Grafana Cloud   │  │           STREAMLIT DASHBOARD              │
│                  │  │                                            │
│  Pipeline health │  │  Page 1: Smart Visit Scorer                │
│  Kafka lag       │  │  ├── City selector (8 cities)              │
│  DAG run times   │  │  ├── Visit Score gauge (0-100)             │
│  Anomaly scores  │  │  ├── 4 metric cards                        │
│  per city        │  │  └── Plain-English AI reasoning            │
│  Alert rates     │  │                                            │
│                  │  │  Page 2: Real-Time Anomaly Alert           │
│  (MLOps layer)   │  │  ├── 6-channel live time-series chart      │
│                  │  │  ├── Anomaly score overlay + threshold      │
│                  │  │  ├── FSM state timeline bar                 │
│                  │  │  └── Channel contribution breakdown         │
└──────────────────┘  └────────────────────────────────────────────┘
```

---

## The ML Core

### LSTM Autoencoder (6-channel)

The anomaly detection model is an unsupervised LSTM Autoencoder trained exclusively on normal operating data — no labeled anomalies required. One model is trained per city to capture each city's unique environmental baseline.

```
Input: (batch, window=50, channels=6)
       temperature_c | humidity_pct | wind_speed_kmh
       precipitation_mm | pm25 | pm10
              │
              ▼
┌─────────────────────────┐
│  Encoder                │
│  LSTM layer 1 (h=64)    │
│  LSTM layer 2 (h=64)    │
│  Linear → latent (16)   │
└─────────────────────────┘
              │
              ▼ latent (dim=16)
              │
┌─────────────────────────┐
│  Decoder                │
│  Linear → hidden (64)   │
│  LSTM layer 1 (h=64)    │
│  LSTM layer 2 (h=64)    │
│  Linear → output (6)    │
└─────────────────────────┘
              │
              ▼
Reconstruction error → anomaly score
Channel contributions → which sensor is anomalous
```

**Training data:** 30 days of historical OpenMeteo + OpenAQ data per city
**Threshold:** 95th percentile of validation reconstruction error
**Window size:** 50 timesteps (250 minutes of sensor history)

### Finite State Machine Alert Engine

```
NORMAL ──[score > threshold, 1 window]──────────► SUSPICIOUS
SUSPICIOUS ──[score > threshold, 3 consecutive]──► ALERT
ALERT ──[score > 1.5× threshold, 5 windows]──────► CONFIRMED
Any state ──[score below threshold, 5 windows]───► NORMAL
```

FSM state per city is stored in Redis for instant access. Every transition is logged to Supabase `alert_events` table.

### Visit Score Formula

```
base_score = 100 - (normalized_anomaly_score × 40)

state_penalty:
  SUSPICIOUS  → -10
  ALERT       → -20
  CONFIRMED   → -35

time_bonus:
  10:00–16:00 → +10 (peak visiting hours)

visit_score = clamp(base_score - state_penalty + time_bonus, 0, 100)
```

---

## Project Structure

```
citypulse-switzerland/
├── dags/
│   └── sensor_pipeline_dag.py       # Airflow DAG — runs every 5 min
├── data/
│   ├── fetch_weather.py             # OpenMeteo API client
│   ├── fetch_airquality.py          # OpenAQ API client
│   └── cities_config.py             # 8 cities with lat/lon
├── kafka/
│   ├── producer.py                  # Publishes sensor readings
│   └── consumer.py                  # Consumes + writes to Supabase/Redis
├── database/
│   ├── supabase_client.py           # Postgres operations
│   ├── redis_client.py              # Upstash REST cache operations
│   └── migrations.sql               # Table definitions
├── models/
│   ├── lstm_autoencoder.py          # 6-channel LSTM AE architecture
│   ├── train_models.py              # Trains one model per city
│   ├── inference_engine.py          # Loads models, runs inference
│   ├── alert_engine.py              # FSM state machine
│   └── saved_models/                # 8 × .pt + scaler files
├── huggingface_space/
│   ├── app.py                       # FastAPI inference server
│   ├── Dockerfile                   # HF Spaces Docker config
│   ├── requirements.txt
│   └── models/                      # Model files for HF deployment
├── streamlit_app/
│   ├── app.py                       # Main Streamlit app
│   ├── pages/
│   │   ├── 01_visit_scorer.py       # Smart Visit Scorer page
│   │   └── 02_anomaly_alert.py      # Real-Time Anomaly Alert page
│   └── components/
│       ├── gauge_chart.py           # Plotly gauge component
│       ├── timeseries_chart.py      # 6-channel live chart
│       └── fsm_timeline.py          # FSM state colour bar
├── tests/
│   ├── test_fetch_weather.py
│   ├── test_kafka_producer.py
│   ├── test_supabase_client.py
│   ├── test_inference_engine.py
│   └── test_alert_engine.py
├── .env                             # All credentials — never committed
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Technology Stack

| Layer | Tool | Why |
|-------|------|-----|
| Stream ingestion | Apache Kafka (Confluent Cloud) | Industry-standard event streaming — same pattern used in IoT sensor pipelines at scale |
| Orchestration | Apache Airflow (Docker) | DAG-based pipeline scheduling — most demanded DE skill |
| Time-series DB | Supabase (PostgreSQL) | Free Postgres + Realtime subscriptions — updates UI without polling |
| Cache | Redis (Upstash) | Sub-10ms anomaly state reads — hot/cold storage separation pattern |
| Model hosting | HuggingFace Spaces | Free production ML inference endpoint — FastAPI + Docker |
| Monitoring | Grafana Cloud | MLOps pipeline health dashboard — standard in production ML teams |
| Frontend | Streamlit Cloud | Rapid ML app deployment — live public URL |
| ML framework | PyTorch 2.0 | LSTM Autoencoder training and inference |
| Data APIs | OpenMeteo + OpenAQ | Free, no API key, real physical sensor stations |

**Total infrastructure cost: $0** — all services on free tiers.

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- Docker Desktop (for local Airflow)
- Git

### Account Setup Required

| Service | URL | Free tier |
|---------|-----|-----------|
| Supabase | supabase.com | 500MB DB, forever free |
| Upstash Redis | upstash.com | 10K requests/day, forever free |
| Confluent Kafka | confluent.io | $400 credits / 30 days |
| HuggingFace | huggingface.co | CPU Basic Spaces, forever free |
| Grafana Cloud | grafana.com | 3 users, forever free |
| Streamlit Cloud | streamlit.io | Public apps, forever free |

### Installation

```bash
git clone https://github.com/shradhanjalipradhan/citypulse-switzerland
cd citypulse-switzerland
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root:

```env
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
SUPABASE_DB_URL=postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres

# Redis (Upstash)
UPSTASH_REDIS_URL=https://xxxx.upstash.io
UPSTASH_REDIS_TOKEN=your_token

# Kafka (Confluent)
KAFKA_BOOTSTRAP_SERVERS=pkc-xxxx.eu-west-1.aws.confluent.cloud:9092
KAFKA_API_KEY=your_api_key
KAFKA_API_SECRET=your_api_secret
KAFKA_TOPIC_SENSOR=raw-sensor-data
KAFKA_TOPIC_ANOMALY=anomaly-results

# HuggingFace
HF_TOKEN=hf_xxxx
HF_USERNAME=shradhanjalipradhan
HF_SPACE_NAME=citypulse-inference

# App config
CITIES=Zurich,Geneva,Bern,Lucerne,Basel,Interlaken,Lausanne,Zermatt
MODEL_WINDOW_SIZE=50
MODEL_INPUT_DIM=6
ANOMALY_THRESHOLD_PERCENTILE=95
REFRESH_INTERVAL_SECONDS=300
```

### Running the Pipeline

```bash
# Step 1 — Create Supabase tables
python database/supabase_client.py --migrate

# Step 2 — Train all 8 city models (takes ~15 minutes on CPU)
python models/train_models.py

# Step 3 — Start Airflow locally
docker run -d -p 8080:8080 --name airflow \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=False \
  apache/airflow:2.8.0 standalone

# Step 4 — Deploy inference API to HuggingFace
python huggingface_space/deploy.py

# Step 5 — Run Streamlit app
streamlit run streamlit_app/app.py
```

---

## Data Flow (every 5 minutes)

```
1. Airflow DAG triggers
   └── fetch_weather.py pulls OpenMeteo for all 8 cities
   └── fetch_airquality.py pulls OpenAQ for all 8 cities

2. Kafka producer publishes 8 JSON messages to raw-sensor-data topic
   Message schema: {city, timestamp, temperature_c, humidity_pct,
                    wind_speed_kmh, precipitation_mm, pm25, pm10}

3. Kafka consumer reads messages
   └── Writes raw readings to Supabase sensor_readings table

4. Inference engine reads latest 50 readings per city from Supabase
   └── Calls HuggingFace /predict endpoint
   └── Receives anomaly_score + channel_contributions + fsm_state

5. AlertEngine updates FSM state per city
   └── Computes visit_score
   └── Logs transitions to Supabase alert_events

6. Results stored:
   └── Supabase anomaly_scores table (permanent history)
   └── Redis city:{name}:* keys (600s TTL cache)

7. Streamlit app reads:
   └── Redis for current state (instant, <10ms)
   └── Supabase for 24hr history chart
   └── Supabase Realtime pushes updates to UI without refresh
```

---

## Results — Model Performance

Training results on 30 days of historical data per city:

| City | Val Loss | Threshold | Training epochs |
|------|----------|-----------|-----------------|
| Zurich | — | — | 60 |
| Geneva | — | — | 60 |
| Bern | — | — | 60 |
| Lucerne | — | — | 60 |
| Basel | — | — | 60 |
| Interlaken | — | — | 60 |
| Lausanne | — | — | 60 |
| Zermatt | — | — | 60 |

*Table populated after training completes. Update with actual numbers from `train_models.py` output.*

---

## Companion Projects

This project is part of a three-project water leak / sensor anomaly detection series:

**Project 1 — Foundation model**
[LSTM-Autoencoder-multivariate-sensor-anomaly-detector](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector)
LSTM Autoencoder on synthetic 4-channel building sensor data. F1=0.814, all 3/3 leak events detected. The architecture CityPulse extends.

**Project 2 — Graph localization** *(coming soon)*
[pipe-network-gnn-localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer)
GraphSAGE GNN on a 20-node pipe network topology. Identifies *where* a fault originated, not just *that* one exists.

**Project 3 — CityPulse (this repo)**
Full production stack: Kafka + Airflow + Supabase + Redis + HuggingFace + Grafana + Streamlit on real public sensor data.

---

## Future Roadmap

### v1.1 — Restaurant & Festival Integration
- **Personalised Restaurant Finder**: Claude AI generates top 5 restaurant recommendations per city based on user food preferences (fondue, vegan, halal, fine dining). Uses OpenStreetMap Overpass API for live restaurant data — always current, never stale.
- **Festival & Events Radar**: Switzerland Tourism open data feed for live events and festivals. AI matches events to user interests. Outdoor events get a weather suitability score from the anomaly model.
- **Crowd Index**: Proxy signal from time-of-day + day-of-week + local holidays + active events count. Feeds into the Visit Score formula.

### v1.2 — Enhanced ML Pipeline
- **Temporal GNN layer**: Add a graph neural network over the city network (cities as nodes, geographical proximity as edges) to detect regional weather anomaly patterns that span multiple cities simultaneously.
- **Adaptive thresholding**: Monthly automated retraining of the anomaly threshold on recent normal data. The model's definition of "normal" stays current with seasonal drift.
- **Uncertainty quantification**: Monte Carlo dropout at inference time to produce calibrated confidence intervals on anomaly scores, not just point predictions.
- **Cross-city transfer learning**: Fine-tune thresholds and scalers per city while keeping LSTM weights frozen. New city onboarding time drops from hours to minutes.

### v1.3 — Production Hardening
- **Kubernetes deployment**: Move from Docker Compose to a Kubernetes cluster on GKE free tier. Horizontal pod autoscaling for the inference layer during peak traffic.
- **Feature store**: Integrate Feast (open source) as a feature store layer between the Kafka consumer and the inference engine. Enables feature reuse across multiple model versions.
- **A/B model testing**: Deploy two model versions simultaneously, split inference traffic 80/20, compare anomaly detection performance on live data before full rollout.
- **dbt for data transformation**: Replace raw SQL in Supabase with dbt models. Enables version-controlled, tested data transformations — the production standard for analytics engineering.

### v1.4 — User Features
- **User accounts**: Supabase Auth for saved city preferences, alert subscriptions, and personalised visit history.
- **Push notifications**: When a watched city hits ALERT state, send a push notification via Pushover free tier.
- **Mobile-responsive UI**: Rebuild the Streamlit frontend as a Next.js app for proper mobile experience and faster load times.
- **Historical anomaly explorer**: Interactive timeline letting users explore past anomaly events per city — what caused them, how long they lasted, what the channel breakdown showed.

### v2.0 — Water Infrastructure Extension
The ultimate extension of this architecture: apply the same pipeline to actual building water sensor data. The only changes needed are the data source (MQTT broker instead of OpenMeteo API) and the sensor channels (pressure, flow, temperature, vibration instead of weather channels). The Kafka ingestion layer, Airflow orchestration, LSTM model architecture, FSM alert engine, Supabase storage, and Streamlit dashboard are all reusable as-is.

This is the architecture that Paul Beckers and Marguerite Benoist's startup is building — CityPulse is the proof of concept.

---

## Architecture Decisions

**Why Kafka over direct API polling?**
Kafka decouples the data producers from consumers. Multiple consumers can independently read the same sensor stream — the inference engine, the Supabase writer, and a future notification service all run independently without coordination. This is the production IoT ingestion pattern.

**Why Redis + Supabase instead of just Supabase?**
Supabase (Postgres) is authoritative but has query latency of 50–200ms. The Streamlit app refreshes every 5 minutes but the current state needs to be readable in <10ms for a snappy UI. Redis holds the hot state (current anomaly score, FSM state, visit score) with sub-10ms reads. Supabase holds the cold history for charts. This hot/cold separation is a standard production pattern.

**Why HuggingFace Spaces for model serving instead of running inference locally?**
Hosting the model on HF Spaces means the inference endpoint is available 24/7 without a local machine running. It also demonstrates the MLOps skill of deploying a model as a REST API — a fundamental skill that goes beyond just training models.

**Why unsupervised LSTM Autoencoder instead of supervised classification?**
No labeled anomaly data exists at deployment time. The unsupervised reconstruction approach requires only normal operating data to bootstrap, which is available from the first day of data collection.

---

## Contributing

Contributions welcome. Open an issue first to discuss what you would like to change.

---

## Author

**Shradhanjali Pradhan**
AI/ML Engineer | MSc Applied Data Analytics, Boston University
[LinkedIn](https://linkedin.com/in/shradhanjalipradhan) | [GitHub](https://github.com/shradhanjalipradhan)

*Part of a water leak detection and urban sensor anomaly detection research series.*

---

*Built with free-tier cloud infrastructure — $0 total cost.*
