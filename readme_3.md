# CityPulse Switzerland — Day 3: Streamlit Dashboard

> The user-facing layer of CityPulse — a real-time web application that surfaces Smart Visit Scores and live anomaly alerts for 8 Swiss cities. Powered by the Day 1 data pipeline and Day 2 ML inference layer.

[![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-FF4B4B.svg)](https://streamlit.io)
[![Live App](https://img.shields.io/badge/Live-App-green.svg)](https://citypulse-switzerland.streamlit.app)

---

## What Day 3 Builds

Day 1 built the data pipeline. Day 2 built the ML brain. Day 3 builds what users actually see and interact with — a clean, fast, real-time Streamlit dashboard with two core pages:

- **Smart Visit Scorer** — Select any Swiss city, get an instant 0–100 visit score driven by the LSTM anomaly model, with plain-English reasoning and current weather + air quality metrics
- **Real-Time Anomaly Alert** — Live 6-channel sensor chart with anomaly score overlay, FSM state timeline, and per-channel contribution breakdown — updating every 5 minutes automatically

---

## Live App

**Streamlit Cloud:** [citypulse-switzerland.streamlit.app](https://citypulse-switzerland.streamlit.app) *(coming soon)*

Default city on load: **Zurich** — the startup's primary pilot city.

---

## App Architecture

```
User opens Streamlit app
        │
        ▼
City selector (sidebar)
        │
        ├──► Redis (sub-10ms)
        │    city:{name}:visit_score
        │    city:{name}:fsm_state
        │    city:{name}:latest_reading
        │         │
        │         ▼
        │    Page 1: Smart Visit Scorer
        │    (current state, instant load)
        │
        └──► Supabase (historical query)
             SELECT * FROM anomaly_scores
             WHERE city = ? ORDER BY timestamp DESC
             LIMIT 288 (last 24 hours)
                  │
                  ▼
             Page 2: Real-Time Anomaly Alert
             (24hr chart, 5-min auto-refresh)

Supabase Realtime subscription
→ pushes new anomaly_scores rows to UI
→ chart updates without full page reload
```

---

## Page 1 — Smart Visit Scorer

The homepage. Answers the question: "Should I visit this city today?"

### Layout

```
┌─────────────────────────────────────────────────┐
│  CityPulse Switzerland          [City selector] │
├─────────────────────────────────────────────────┤
│                                                 │
│         ZURICH VISIT SCORE                      │
│              ╔══════╗                           │
│              ║  78  ║  ← Plotly gauge (0-100)   │
│              ╚══════╝                           │
│           Good time to visit                    │
│                                                 │
├──────────┬──────────┬──────────┬────────────────┤
│ Temp     │ Humidity │ Wind     │ Air Quality    │
│ 3.5°C    │ 87%      │ 7.3 km/h │ Good           │
│ (normal) │ (high)   │ (calm)   │ PM10: 4.8      │
├──────────┴──────────┴──────────┴────────────────┤
│  Anomaly State: NORMAL  ●●●●○  (4/5 windows)   │
├─────────────────────────────────────────────────┤
│  AI Reasoning:                                  │
│  "Clear skies and calm winds make this a        │
│   good day to visit Zurich. Air quality is      │
│   within normal range. No anomalies detected    │
│   in the last 30 minutes."                      │
├─────────────────────────────────────────────────┤
│  Last updated: 2 minutes ago  [Auto-refresh ON] │
└─────────────────────────────────────────────────┘
```

### Visit Score Color Coding

| Score | Color | Label |
|-------|-------|-------|
| 80–100 | Green | Great time to visit |
| 60–79 | Amber | Good — minor caution |
| 40–59 | Orange | Consider alternatives |
| 0–39 | Red | Not recommended today |

### FSM State Badge

| State | Badge | Meaning |
|-------|-------|---------|
| NORMAL | Green dot | All sensors within baseline |
| SUSPICIOUS | Amber dot | One anomalous window detected |
| ALERT | Orange dot | 3 consecutive anomalous windows |
| CONFIRMED | Red dot | Sustained anomaly — significant event |

---

## Page 2 — Real-Time Anomaly Alert

The technical deep-dive page. Shows exactly what the LSTM model is seeing.

### Layout

```
┌─────────────────────────────────────────────────┐
│  Real-Time Anomaly Monitor — Zurich             │
│  FSM State: NORMAL  │  Next refresh: 4:32       │
├─────────────────────────────────────────────────┤
│                                                 │
│  6-Channel Sensor Time Series (last 24 hrs)     │
│  ┌───────────────────────────────────────────┐  │
│  │ temperature_c ──────────────────────────  │  │
│  │ humidity_pct  ──────────────────────────  │  │
│  │ wind_speed    ──────────────────────────  │  │
│  │ precipitation ──────────────────────────  │  │
│  │ pm25          ──────────────────────────  │  │
│  │ pm10          ──────────────────────────  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  Anomaly Score (last 24 hrs)                    │
│  ┌───────────────────────────────────────────┐  │
│  │                    ▲ threshold (1.353)    │  │
│  │ score ─────────────────────────────────── │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  FSM State Timeline                             │
│  ████████████████████████████ NORMAL (green)   │
│                                                 │
│  Channel Contributions (latest window)          │
│  wind_speed_kmh  ████████████  34%             │
│  humidity_pct    ████████      18%             │
│  pm25            ██████████    21%             │
│  temperature_c   ██████        12%             │
│  pm10            ████████      8%              │
│  precipitation   ██████        7%              │
└─────────────────────────────────────────────────┘
```

### Auto-Refresh Logic

- Streamlit `st.rerun()` fires every 300 seconds (5 minutes)
- Supabase Realtime subscription pushes new rows instantly
- Redis provides current state in <10ms so the page loads fast
- Countdown timer shows seconds until next refresh

---

## Sidebar — City Comparison

Always visible on both pages. Shows all 8 cities at a glance:

```
┌─────────────────────┐
│  All Cities         │
├─────────────────────┤
│ ● Zurich      78   │
│ ● Geneva      82   │
│ ○ Bern        71   │
│ ● Lucerne     85   │
│ ● Basel       74   │
│ ● Interlaken  69   │
│ ● Lausanne    80   │
│ ● Zermatt     77   │
├─────────────────────┤
│ ● NORMAL  ○ ALERT  │
└─────────────────────┘
```

Click any city to switch the main view instantly.

---

## Technical Implementation

### Data Reading Strategy

```python
# Fast path — Redis for current state (< 10ms)
city_state = redis_client.get_city_state(city)
visit_score = city_state["visit_score"]
fsm_state = city_state["fsm_state"]

# Slow path — Supabase for 24hr history (50-200ms)
history = supabase_client.get_latest_scores(city, hours=24)

# Realtime — Supabase subscription for live updates
supabase.realtime.subscribe("anomaly_scores")
```

### Plotly Charts Used

- **Visit Score**: `go.Indicator` with gauge mode, color-coded by score range
- **Sensor time series**: `go.Scatter` with secondary y-axis for anomaly score overlay
- **FSM timeline**: `go.Bar` with color mapping per state
- **Channel contributions**: `go.Bar` horizontal with percentage labels

### Streamlit Components

```python
st.set_page_config(layout="wide", page_title="CityPulse Switzerland")
st.sidebar  # City selector + all-cities comparison
st.plotly_chart(gauge, use_container_width=True)
st.metric("Visit Score", 78, delta="+3 from last hour")
st.dataframe(history, hide_index=True)
st.empty()  # Auto-refresh container
```

---

## Deployment — Streamlit Cloud

### Setup (5 minutes)

1. Go to **share.streamlit.io**
2. Connect your GitHub account
3. Select repo: `shradhanjalipradhan/CityPulse`
4. Main file: `streamlit_app/app.py`
5. Add secrets (equivalent to .env):

```toml
# .streamlit/secrets.toml
SUPABASE_URL = "https://mgawmfmhyfohkfjkrfft.supabase.co"
SUPABASE_ANON_KEY = "your_anon_key"
UPSTASH_REDIS_URL = "https://xxxx.upstash.io"
UPSTASH_REDIS_TOKEN = "your_token"
HF_SPACE_URL = "https://shradhanjalipradhan-citypulse-inference.hf.space"
```

6. Click **Deploy** — live URL in under 2 minutes

### Why Streamlit Cloud over other options

- Zero config — connects directly to GitHub, redeploys on every push
- Free forever for public repos
- Handles secrets securely without exposing them in code
- Native support for `st.rerun()` auto-refresh pattern

---

## Day 3 Project Structure

```
citypulse-switzerland/
├── streamlit_app/
│   ├── app.py                    # Main app — page routing + sidebar
│   ├── pages/
│   │   ├── 01_visit_scorer.py    # Smart Visit Scorer page
│   │   └── 02_anomaly_alert.py   # Real-Time Anomaly Alert page
│   ├── components/
│   │   ├── gauge_chart.py        # Plotly gauge component
│   │   ├── sensor_chart.py       # 6-channel time series chart
│   │   ├── fsm_timeline.py       # FSM state colour bar
│   │   └── city_sidebar.py       # All-cities comparison sidebar
│   └── utils/
│       ├── redis_reader.py       # Fast state reads from Redis
│       └── supabase_reader.py    # Historical data from Supabase
├── .streamlit/
│   └── secrets.toml              # Credentials for Streamlit Cloud
└── ... (Day 1 + Day 2 files unchanged)
```

---

## Pre-Flight Checklist Before Building Day 3

- [ ] Day 2 inference running — Supabase anomaly_scores has rows
- [ ] Redis has 8 city states with visit_score and fsm_state
- [ ] HF Space is live at citypulse-inference.hf.space
- [ ] Streamlit Cloud account created at share.streamlit.io
- [ ] GitHub repo is Public
- [ ] All credentials ready for .streamlit/secrets.toml

---

## Quickstart

```bash
# Install Streamlit locally
pip install streamlit plotly

# Run locally first
streamlit run streamlit_app/app.py

# Deploy to Streamlit Cloud
# Go to share.streamlit.io → connect GitHub → select repo → deploy
```

---

## What the Interview Demo Looks Like

Open your laptop, share screen, go to the live Streamlit URL:

1. **City selector defaults to Zurich** — show the visit score gauge
2. **Switch to Geneva** — score changes, reasoning updates
3. **Go to Anomaly Alert page** — show the live sensor chart and anomaly score
4. **Point to the FSM timeline** — "This is the same state machine from my LSTM project, running on real city data"
5. **Show the channel contributions** — "When wind_speed is the top contributor, the recommendation shifts to indoor activities"
6. **Open the HF Space URL** — show the raw inference API responding in real time

Total demo time: 90 seconds. Every component is live, every number is real.

---

## Companion Projects

- **Project 1**: [LSTM-Autoencoder](https://github.com/shradhanjalipradhan/LSTM-Autoencoder-multivariate-sensor-anomaly-detector) — F1=0.814, foundation model
- **Project 2**: [GNN Localizer](https://github.com/shradhanjalipradhan/pipe-network-gnn-localizer) — GraphSAGE pipe network fault localization *(coming soon)*
- **Project 3**: [CityPulse Switzerland](https://github.com/shradhanjalipradhan/CityPulse) — This repo

---

*Day 1: Data pipeline — Kafka + Airflow + Supabase + Redis*
*Day 2: ML layer — LSTM models + HuggingFace Spaces + Alert Engine*
*Day 3: Dashboard — Streamlit Cloud + Smart Visit Scorer + Anomaly Alert (this file)*


echo ".streamlit/secrets.toml" >> .gitignore
```

---

**Thing 2 — GitHub repo must be Public**

Streamlit Cloud deploys from public repos on the free tier. Go to **github.com/shradhanjalipradhan/CityPulse → Settings → Danger Zone → Change visibility → Make public**

---

**Thing 3 — The main file path**

When Streamlit Cloud asks for the main file, enter exactly:
```
streamlit_app/app.py
```

---

Once those 3 are ready, paste this in Claude Code:
```
Build the complete Day 3 Streamlit dashboard for CityPulse 
Switzerland. Read credentials from .streamlit/secrets.toml.

Create this structure:
streamlit_app/
├── app.py
├── pages/
│   ├── 01_visit_scorer.py
│   └── 02_anomaly_alert.py
├── components/
│   ├── gauge_chart.py
│   ├── sensor_chart.py
│   ├── fsm_timeline.py
│   └── city_sidebar.py
└── utils/
    ├── redis_reader.py
    └── supabase_reader.py

REQUIREMENTS:

1. app.py
- st.set_page_config(layout="wide", 
  page_title="CityPulse Switzerland",
  page_icon="🏔️")
- Sidebar: city selector dropdown (8 Swiss cities)
  default: Zurich
- Sidebar: all-cities mini comparison table showing
  visit_score and fsm_state for all 8 cities
  reads from Redis via redis_reader.get_all_city_states()
- Route to pages based on sidebar navigation

2. utils/redis_reader.py
- Reads from Upstash Redis REST API using credentials
  from st.secrets
- get_city_state(city): returns dict with
  visit_score, fsm_state, anomaly_score, timestamp
- get_all_city_states(): returns all 8 cities states
- get_latest_reading(city): returns latest sensor values

3. utils/supabase_reader.py
- Reads from Supabase using credentials from st.secrets
- get_anomaly_history(city, hours=24): returns DataFrame
  of anomaly_scores rows for last N hours
- get_sensor_history(city, hours=24): returns DataFrame
  of sensor_readings rows for last N hours
- get_latest_anomaly(city): returns most recent row

4. pages/01_visit_scorer.py
LAYOUT:
- Large Plotly gauge chart (0-100) color coded:
  80-100: green, 60-79: amber, 40-59: orange, 0-39: red
- 4 metric cards in a row:
  Temperature, Humidity, Wind Speed, Air Quality (PM10)
  Each shows current value + "normal/high/low" label
- FSM state badge with color and plain-English meaning
- AI reasoning text box:
  Generate a 2-sentence plain English explanation based on:
  visit_score, fsm_state, temperature, humidity, fsm_state
  Example: "Clear conditions in Zurich today with no anomalies
  detected. Air quality is within normal range — a good time
  to visit."
- Last updated timestamp + auto-refresh countdown
- Reads from Redis (fast path for current state)

5. pages/02_anomaly_alert.py  
LAYOUT:
- Header: city name + current FSM state badge
- 6-channel sensor time series chart (Plotly):
  All 6 channels on one chart with secondary y-axis
  X-axis: last 24 hours of timestamps
  Color per channel, legend, hover tooltips
- Anomaly score chart below:
  Line chart with threshold line (city-specific threshold)
  Shade area above threshold in light red
  Shade area below threshold in light green
- FSM state timeline:
  Horizontal bar chart colored by state
  NORMAL=green, SUSPICIOUS=amber, ALERT=orange, CONFIRMED=red
- Channel contributions horizontal bar chart:
  Shows which sensor drove the latest anomaly score
  Percentages add to 100%
- Auto-refresh every 300 seconds using st.rerun()
- Shows countdown timer to next refresh
- Reads from Supabase for history
- Reads from Redis for current state

6. requirements.txt additions
Add to existing requirements.txt:
streamlit==1.29.0
plotly==5.18.0
supabase==2.3.0
requests==2.31.0

7. .streamlit/config.toml
[theme]
primaryColor = "#1F4E79"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

After building all files:
1. Run locally: streamlit run streamlit_app/app.py
2. Confirm both pages load without errors
3. Confirm visit scorer shows Zurich score
4. Confirm anomaly alert shows 24hr chart
5. Then push to GitHub:
   cd C:\Users\Venkata\Desktop\CityPulse-repo
   Copy all streamlit_app/ files
   git add .
   git commit -m "Day 3: Streamlit dashboard with Visit Scorer and Anomaly Alert"
   git push origin master

Load ALL credentials from st.secrets
Never hardcode any credential
Handle missing Redis/Supabase data gracefully with 
st.warning() messages
Default city is always Zurich