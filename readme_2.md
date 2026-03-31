# CityPulse Switzerland — Day 2: ML Layer

> LSTM Autoencoder anomaly detection models for 8 Swiss cities, served as a production REST API on HuggingFace Spaces. This is the intelligence layer that powers the Smart Visit Scorer and Real-Time Anomaly Alerts.

---

## What Day 2 Builds

Day 1 built the data pipeline — Kafka ingesting, Airflow orchestrating, Supabase storing, Redis caching. Day 2 adds the ML brain on top of that pipeline:

- **8 trained LSTM Autoencoder models** — one per Swiss city, trained on 30 days of real historical weather + air quality data
- **FastAPI inference server** — hosted on HuggingFace Spaces, accepts sensor windows and returns anomaly scores
- **Alert Engine** — Finite State Machine (NORMAL → SUSPICIOUS → ALERT → CONFIRMED) running per city
- **Inference Engine** — reads latest sensor data from Supabase, calls HF endpoint, writes anomaly scores back to Supabase and Redis
- **Airflow integration** — inference runs automatically every 5 minutes as a 4th task in the existing DAG

---

## Architecture Added in Day 2

```
Supabase sensor_readings
        │
        ▼
Inference Engine
(reads last 50 readings per city)
        │
        ▼
HuggingFace Spaces
FastAPI /predict endpoint
(LSTM Autoencoder — 6 channels)
        │
        ▼
anomaly_score + channel_contributions
        │
        ▼
Alert Engine FSM
(NORMAL → SUSPICIOUS → ALERT → CONFIRMED)
        │
        ▼
visit_score computed (0–100)
        │
        ├──► Supabase anomaly_scores table
        └──► Redis city:{name}:fsm_state + visit_score
```

---

## The LSTM Autoencoder

### Architecture

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
│  Dropout (0.2)          │
│  Linear → latent (16)   │
└─────────────────────────┘
              │
              ▼ latent vector (dim=16)
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

### Why Unsupervised

Weather anomalies in Swiss cities are rare events with no labeled ground truth. Training only on normal operating data means the model learns what normal looks like — any deviation produces high reconstruction error. No labeled anomalies needed to bootstrap.

### Training Data

- **Source**: 30 days of historical OpenMeteo + OpenAQ data per city
- **Split**: 70% train / 15% validation / 15% test — no shuffling (time-series)
- **Threshold**: 95th percentile of validation reconstruction error
- **One model per city**: Each city has a unique climate baseline (Zermatt at 1,608m altitude vs Geneva at lake level)

---

## Alert Engine FSM

```
NORMAL ──[score > threshold, 1 window]──────────► SUSPICIOUS
SUSPICIOUS ──[score > threshold, 3 consecutive]──► ALERT
ALERT ──[score > 1.5× threshold, 5 windows]──────► CONFIRMED
Any state ──[score below threshold, 5 windows]───► NORMAL
```

State stored in Redis per city. Every transition logged to Supabase `alert_events` table.

---

## Visit Score Formula

```
base = 100 - (normalized_anomaly_score × 40)

penalties:
  SUSPICIOUS  → -10
  ALERT       → -20
  CONFIRMED   → -35

bonus:
  hour 10–16  → +10  (peak visiting hours)

visit_score = clamp(base + bonus - penalty, 0, 100)
```

---

## HuggingFace Spaces Deployment

The inference server runs as a FastAPI app inside a Docker container on HuggingFace Spaces CPU Basic (free tier).

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/predict` | Run inference for one city |
| GET | `/health` | Check server status |
| GET | `/cities` | List supported cities |
| GET | `/models` | Show loaded model info |

**Request format:**
```json
{
  "city": "Zurich",
  "window": [[3.5, 87.0, 7.3, 0.0, 5.0, 4.77], ...]
}
```

**Response format:**
```json
{
  "city": "Zurich",
  "anomaly_score": 0.142,
  "fsm_state": "NORMAL",
  "visit_score": 78,
  "threshold": 0.168,
  "channel_contributions": {
    "temperature_c": 0.021,
    "humidity_pct": 0.018,
    "wind_speed_kmh": 0.034,
    "precipitation_mm": 0.012,
    "pm25": 0.031,
    "pm10": 0.026
  }
}
```

---

## Model Training Results

| City | Val Loss | Threshold | Epochs | Status |
|------|----------|-----------|--------|--------|
| Zurich | — | — | 60 | — |
| Geneva | — | — | 60 | — |
| Bern | — | — | 60 | — |
| Lucerne | — | — | 60 | — |
| Basel | — | — | 60 | — |
| Interlaken | — | — | 60 | — |
| Lausanne | — | — | 60 | — |
| Zermatt | — | — | 60 | — |

*Update this table after running `python models/train_models.py`*

---

## Day 2 Project Structure

```
citypulse-switzerland/
├── models/
│   ├── lstm_autoencoder.py        # 6-channel LSTM AE architecture
│   ├── train_models.py            # Trains one model per city
│   ├── inference_engine.py        # Reads Supabase, calls HF, writes results
│   ├── alert_engine.py            # FSM state machine per city
│   └── saved_models/
│       ├── zurich_lstm.pt
│       ├── zurich_scaler.pkl
│       └── ... (8 cities × 2 files each)
├── huggingface_space/
│   ├── app.py                     # FastAPI inference server
│   ├── Dockerfile                 # HF Spaces Docker config
│   ├── requirements.txt           # Space-specific deps
│   └── models/                    # Model files copied here
├── dags/
│   └── sensor_pipeline_dag.py     # Updated with run_inference task
└── ... (Day 1 files unchanged)
```

---

## Pre-Flight Checklist Before Running Day 2

Before pasting the Claude Code prompt, confirm all of these:

- [ ] Day 1 pipeline confirmed working (Kafka producer publishes 8 cities)
- [ ] Supabase has sensor_readings rows (check Table Editor)
- [ ] Redis has 8 city states (run `python database/redis_client.py --test`)
- [ ] HuggingFace Space created at `shradhanjalipradhan/citypulse-inference`
- [ ] HF_TOKEN in .env is a Write token
- [ ] Docker Desktop is running
- [ ] At least 500MB free disk space for model files
- [ ] .env file has all credentials filled in

---

## Quickstart

```bash
# Step 1 — Train all 8 models (15–20 minutes on CPU)
python models/train_models.py

# Step 2 — Test inference locally
python models/inference_engine.py --test

# Step 3 — Deploy to HuggingFace
python huggingface_space/deploy.py

# Step 4 — Test the live endpoint
curl -X POST https://shradhanjalipradhan-citypulse-inference.hf.space/predict \
  -H "Content-Type: application/json" \
  -d '{"city":"Zurich","window":[[3.5,87,7.3,0,5,4.77]]}'

# Step 5 — Update Airflow DAG with inference task
docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
```

---

## What Changes in the Airflow DAG

Day 1 DAG had 3 tasks:
```
fetch_and_publish → consume_and_store → log_pipeline_health
```

Day 2 DAG adds a 4th task:
```
fetch_and_publish → consume_and_store → run_inference → log_pipeline_health
```

`run_inference` calls `InferenceEngine.run_all_cities()` which:
1. Reads latest 50 readings per city from Supabase
2. Calls HuggingFace `/predict` endpoint
3. Gets anomaly score + FSM state + visit score
4. Writes to Supabase `anomaly_scores` table
5. Updates Redis `city:{name}:fsm_state` and `city:{name}:visit_score`

---

## Companion Projects

- **Project 1**: [LSTM-Autoencoder-multivariate-sensor-anomaly-detector](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector) — F1=0.814, all 3/3 leaks detected. The model architecture this project extends.
- **Project 2**: [pipe-network-gnn-localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer) — GraphSAGE GNN for pipe network fault localization *(coming soon)*
- **Project 3**: [CityPulse Switzerland](https://github.com/shradhanjalipradhan/CityPulse) — This repo. Full production stack.

---

## Tech Stack

| Component | Tool | Free tier |
|-----------|------|-----------|
| ML framework | PyTorch 2.0 | — |
| Model serving | HuggingFace Spaces | CPU Basic, forever free |
| Inference API | FastAPI + Uvicorn | — |
| Container | Docker | — |
| Pipeline orchestration | Apache Airflow | Docker local |

---

*Day 1 README: [pipeline layer](https://github.com/shradhanjalipradhan/CityPulse)*
*Day 3 coming: Streamlit dashboard — Smart Visit Scorer + Real-Time Anomaly Alert*


************************************************************************

# CityPulse Switzerland — Day 2: ML Layer

> LSTM Autoencoder anomaly detection models for 8 Swiss cities, served as a production REST API on HuggingFace Spaces. This is the intelligence layer that powers the Smart Visit Scorer and Real-Time Anomaly Alerts.

---

## What Day 2 Builds

Day 1 built the data pipeline — Kafka ingesting, Airflow orchestrating, Supabase storing, Redis caching. Day 2 adds the ML brain on top of that pipeline:

- **8 trained LSTM Autoencoder models** — one per Swiss city, trained on 30 days of real historical weather + air quality data
- **FastAPI inference server** — hosted on HuggingFace Spaces, accepts sensor windows and returns anomaly scores
- **Alert Engine** — Finite State Machine (NORMAL → SUSPICIOUS → ALERT → CONFIRMED) running per city
- **Inference Engine** — reads latest sensor data from Supabase, calls HF endpoint, writes anomaly scores back to Supabase and Redis
- **Airflow integration** — inference runs automatically every 5 minutes as a 4th task in the existing DAG

---

## Live System Status

| Component | Status | Details |
|-----------|--------|---------|
| HF Space inference API | Live | 8/8 models loaded |
| Supabase sensor_readings | Live | 471+ rows |
| Supabase anomaly_scores | Live | 32+ rows |
| Redis city states | Live | 8/8 cities cached |
| Airflow DAG | Active | Every 5 minutes, 4 tasks |

---

## Architecture Added in Day 2

```
Supabase sensor_readings (471+ rows)
        │
        ▼
Inference Engine
(reads last 50 readings per city)
        │
        ▼
HuggingFace Spaces — citypulse-inference
FastAPI /predict endpoint
(LSTM Autoencoder — 6 channels — 8 models)
        │
        ▼
anomaly_score + channel_contributions
        │
        ▼
Alert Engine FSM
(NORMAL → SUSPICIOUS → ALERT → CONFIRMED)
        │
        ▼
visit_score (0–100)
        │
        ├──► Supabase anomaly_scores table
        └──► Redis city:{name}:fsm_state + visit_score

Airflow DAG (every 5 minutes):
fetch_and_publish → consume_and_store → run_inference → log_pipeline_health
```

---

## The LSTM Autoencoder

### Architecture

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
│  Dropout (0.2)          │
│  Linear → latent (16)   │
└─────────────────────────┘
              │
              ▼ latent vector (dim=16)
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

### Why Unsupervised

Weather anomalies in Swiss cities are rare events with no labeled ground truth. Training only on normal operating data means the model learns what normal looks like — any deviation produces high reconstruction error. No labeled anomalies needed to bootstrap.

### Training Data

- **Source**: 30 days of historical OpenMeteo + OpenAQ data per city
- **Split**: 70% train / 15% validation / 15% test — no shuffling (time-series)
- **Threshold**: 95th percentile of validation reconstruction error
- **One model per city**: Each city has a unique climate baseline (Zermatt at 1,608m altitude vs Geneva at lake level)

---

## Model Training Results

Trained on 30 days of real historical data per city. All 8 models trained successfully.

| City | Val Loss | Threshold | Epochs | Notes |
|------|----------|-----------|--------|-------|
| Zurich | 0.7898 | 1.3532 | 60 | Financial hub, dense sensor coverage |
| Geneva | 0.5329 | 0.6289 | 60 | Lowest val loss — stable lake microclimate |
| Bern | 0.7510 | 1.0442 | 60 | Alpine weather patterns |
| Lucerne | 0.9856 | 1.7964 | 60 | Highest threshold — lake valley variability |
| Basel | 0.7525 | 1.2285 | 60 | Rhine valley, industrial signals |
| Interlaken | 0.7457 | 1.4628 | 60 | Alpine valley, extreme weather events |
| Lausanne | 0.6082 | 1.2280 | 60 | Lake Geneva, stable baseline |
| Zermatt | 0.6144 | 1.1882 | 60 | High altitude (1,608m), unique profile |

**Key insight**: Geneva and Lausanne have the lowest val loss — their Lake Geneva microclimate is the most predictable. Lucerne has the highest threshold — the lake valley creates high natural variability that the model correctly learns to tolerate before alerting.

---

## Alert Engine FSM

```
NORMAL ──[score > threshold, 1 window]──────────► SUSPICIOUS
SUSPICIOUS ──[score > threshold, 3 consecutive]──► ALERT
ALERT ──[score > 1.5× threshold, 5 windows]──────► CONFIRMED
Any state ──[score below threshold, 5 windows]───► NORMAL
```

State stored in Redis per city. Every transition logged to Supabase `alert_events` table.

---

## Visit Score Formula

```
base = 100 - (normalized_anomaly_score × 40)

penalties:
  SUSPICIOUS  → -10
  ALERT       → -20
  CONFIRMED   → -35

bonus:
  hour 10–16 UTC → +10  (peak visiting hours)

visit_score = clamp(base + bonus - penalty, 0, 100)
```

---

## HuggingFace Spaces Deployment

Live at: **https://huggingface.co/spaces/shradhanjalipradhan/citypulse-inference**

The inference server runs as a FastAPI app inside a Docker container on HuggingFace Spaces CPU Basic (free tier).

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/predict` | Run inference for one city |
| GET | `/health` | Check server status — models loaded: 8/8 |
| GET | `/cities` | List 8 supported cities |
| GET | `/models` | Show city → threshold mapping |

**Request format:**
```json
{
  "city": "Zurich",
  "window": [[3.5, 87.0, 7.3, 0.0, 5.0, 4.77], ...]
}
```

**Response format:**
```json
{
  "city": "Zurich",
  "anomaly_score": 0.142,
  "fsm_state": "NORMAL",
  "visit_score": 78,
  "threshold": 1.353,
  "channel_contributions": {
    "temperature_c": 0.021,
    "humidity_pct": 0.018,
    "wind_speed_kmh": 0.034,
    "precipitation_mm": 0.012,
    "pm25": 0.031,
    "pm10": 0.026
  }
}
```

---

## Day 2 Project Structure

```
citypulse-switzerland/
├── models/
│   ├── lstm_autoencoder.py        # 6-channel LSTM AE architecture
│   ├── train_models.py            # Trains one model per city
│   ├── inference_engine.py        # Reads Supabase, calls HF, writes results
│   ├── alert_engine.py            # FSM state machine per city
│   └── saved_models/
│       ├── zurich_lstm.pt         # threshold: 1.3532
│       ├── zurich_scaler.pkl
│       ├── zurich_threshold.json
│       ├── geneva_lstm.pt         # threshold: 0.6289
│       ├── bern_lstm.pt           # threshold: 1.0442
│       ├── lucerne_lstm.pt        # threshold: 1.7964
│       ├── basel_lstm.pt          # threshold: 1.2285
│       ├── interlaken_lstm.pt     # threshold: 1.4628
│       ├── lausanne_lstm.pt       # threshold: 1.2280
│       └── zermatt_lstm.pt        # threshold: 1.1882
├── huggingface_space/
│   ├── app.py                     # FastAPI inference server
│   ├── Dockerfile                 # HF Spaces Docker config
│   ├── requirements.txt           # torch==2.4.0, numpy==2.0.0
│   └── models/                    # 8 × .pt + .pkl + .json files
├── dags/
│   └── sensor_pipeline_dag.py     # 4-task DAG including run_inference
└── ... (Day 1 files unchanged)
```

---

## Quickstart

```bash
# Train all 8 models (15–20 minutes on CPU)
python models/train_models.py

# Test inference locally
python models/inference_engine.py --test

# Deploy to HuggingFace
python huggingface_space/deploy.py

# Test live endpoint
curl -X POST \
  https://shradhanjalipradhan-citypulse-inference.hf.space/predict \
  -H "Content-Type: application/json" \
  -d '{"city":"Zurich","window":[]}'

# Update Airflow DAG
docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
```

---

## After Docker Restart

Airflow container is ephemeral. After every Docker restart run:

```powershell
# Restore ML files in container
docker exec --user root airflow mkdir -p /opt/airflow/citypulse/models/saved_models
docker exec --user root airflow chown -R airflow:root /opt/airflow/citypulse/models

# Re-copy model files
docker cp models/saved_models/. airflow:/opt/airflow/citypulse/models/saved_models/
docker cp .env airflow:/opt/airflow/citypulse/.env
docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
```

---

## What Changes in the Airflow DAG

Day 1 had 3 tasks. Day 2 adds a 4th:

```
fetch_and_publish → consume_and_store → run_inference → log_pipeline_health
```

`run_inference` calls `InferenceEngine.run_all_cities()` which:
1. Reads latest 50 readings per city from Supabase
2. Posts to HuggingFace `/predict` endpoint
3. Gets anomaly score + channel contributions + FSM state
4. Computes visit score (0–100)
5. Writes to Supabase `anomaly_scores` table
6. Updates Redis `city:{name}:fsm_state` and `city:{name}:visit_score`

---

## Tech Stack

| Component | Tool | Free tier |
|-----------|------|-----------|
| ML framework | PyTorch 2.4.0 | — |
| Model serving | HuggingFace Spaces | CPU Basic, forever free |
| Inference API | FastAPI + Uvicorn | — |
| Container | Docker | — |
| Pipeline orchestration | Apache Airflow 2.8 | Docker local |

---

## Companion Projects

- **Project 1**: [LSTM-Autoencoder-multivariate-sensor-anomaly-detector](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector) — F1=0.814, all 3/3 leak events detected. The model architecture CityPulse extends.
- **Project 2**: [pipe-network-gnn-localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer) — GraphSAGE GNN for pipe network fault localization *(coming soon)*
- **Project 3**: [CityPulse Switzerland](https://github.com/shradhanjalipradhan/CityPulse) — This repo. Full production stack.

---

*Day 1: Data pipeline — Kafka + Airflow + Supabase + Redis*
*Day 2: ML layer — LSTM models + HuggingFace Spaces + Alert Engine (this file)*
*Day 3 coming: Streamlit dashboard — Smart Visit Scorer + Real-Time Anomaly Alert*