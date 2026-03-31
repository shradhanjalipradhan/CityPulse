I am building CityPulse Switzerland — a real-time urban anomaly detection 
system. My .env file is at ~/Desktop/citypulse-switzerland/.env with all 
credentials filled in. Read the .env file first, then build the complete 
Day 1 data pipeline.

Create this project structure at ~/Desktop/citypulse-switzerland/:

citypulse-switzerland/
├── dags/
│   └── sensor_pipeline_dag.py
├── data/
│   ├── fetch_weather.py
│   ├── fetch_airquality.py
│   └── cities_config.py
├── kafka/
│   ├── producer.py
│   └── consumer.py
├── database/
│   ├── supabase_client.py
│   ├── redis_client.py
│   └── migrations.sql
├── tests/
│   ├── test_fetch_weather.py
│   ├── test_kafka_producer.py
│   └── test_supabase_client.py
├── .env (already exists — do not overwrite)
├── .gitignore
└── requirements.txt

IMPORTANT CREDENTIALS FROM .env:
- Kafka uses SASL_SSL + SCRAM-SHA-256 authentication (Redpanda)
- Redis uses Upstash REST API (not redis-py, use plain requests)
- Supabase uses service key for server-side operations

STEP 1 — database/migrations.sql
Create these exact tables:

CREATE TABLE IF NOT EXISTS sensor_readings (
  id BIGSERIAL PRIMARY KEY,
  city VARCHAR(50) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  temperature_c FLOAT,
  humidity_pct FLOAT,
  wind_speed_kmh FLOAT,
  precipitation_mm FLOAT,
  pm25 FLOAT,
  pm10 FLOAT,
  crowd_index FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS anomaly_scores (
  id BIGSERIAL PRIMARY KEY,
  city VARCHAR(50) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  anomaly_score FLOAT NOT NULL,
  fsm_state VARCHAR(20) NOT NULL,
  visit_score INTEGER NOT NULL,
  temp_contribution FLOAT,
  humidity_contribution FLOAT,
  wind_contribution FLOAT,
  precip_contribution FLOAT,
  pm25_contribution FLOAT,
  pm10_contribution FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_events (
  id BIGSERIAL PRIMARY KEY,
  city VARCHAR(50) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  from_state VARCHAR(20),
  to_state VARCHAR(20),
  anomaly_score FLOAT,
  trigger_channel VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensor_city_time 
  ON sensor_readings (city, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_city_time 
  ON anomaly_scores (city, timestamp DESC);

STEP 2 — data/cities_config.py
Dictionary of 8 Swiss cities:
Zurich (47.3769, 8.5417)
Geneva (46.2044, 6.1432)
Bern (46.9481, 7.4474)
Lucerne (47.0502, 8.3093)
Basel (47.5596, 7.5886)
Interlaken (46.6863, 7.8632)
Lausanne (46.5197, 6.6323)
Zermatt (46.0207, 7.7491)

STEP 3 — data/fetch_weather.py
FetchWeather class using OpenMeteo free API:
- fetch_current(city): returns dict with temperature_c, humidity_pct,
  wind_speed_kmh, precipitation_mm
- fetch_historical(city, days=30): returns DataFrame for model training
- Uses requests library, no API key needed
- Retry logic: 3 attempts with 5 second delay
- Graceful error handling — never crash on single city failure
- Log every fetch with timestamp and city name

STEP 4 — data/fetch_airquality.py
FetchAirQuality class using OpenAQ v3 free API:
- fetch_current(city): returns dict with pm25, pm10
- If no station found for city, return estimated values
  (Zermatt and Interlaken use nearest available station)
- fetch_historical(city, days=30): returns DataFrame
- Same retry and error handling as weather

STEP 5 — kafka/producer.py
SensorDataProducer class:
- Uses confluent-kafka Python library
- SASL_SSL + SCRAM-SHA-256 authentication
- Config loaded from .env:
  bootstrap.servers = KAFKA_BOOTSTRAP_SERVERS
  sasl.username = KAFKA_API_KEY
  sasl.password = KAFKA_API_SECRET
  security.protocol = SASL_SSL
  sasl.mechanism = SCRAM-SHA-256
- publish_sensor_reading(city, weather_data, aq_data):
  publishes JSON to KAFKA_TOPIC_SENSOR
- run_once(): fetches all 8 cities and publishes all readings
- Delivery callback for error logging

STEP 6 — kafka/consumer.py
SensorDataConsumer class:
- Consumes from KAFKA_TOPIC_SENSOR topic
- Writes each message to Supabase sensor_readings table
- Writes latest reading for each city to Redis:
  key: city:{city_name}:latest_reading
  TTL: 600 seconds
- Runs for a configurable duration then exits cleanly
- Handles all Kafka errors gracefully

STEP 7 — database/supabase_client.py
SupabaseClient class:
- Connects using SUPABASE_URL + SUPABASE_SERVICE_KEY
- run_migrations(): reads and executes migrations.sql
- insert_sensor_reading(city, data)
- insert_anomaly_score(city, score_data)
- get_latest_scores(hours=24): returns DataFrame
- get_city_latest(city): returns most recent anomaly score row
- get_recent_readings(city, limit=50): returns last N readings

STEP 8 — database/redis_client.py
RedisClient class using Upstash REST API with plain requests:
- Uses UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN from .env
- Do NOT use redis-py — use requests to call Upstash REST API
- set(key, value, ttl_seconds): stores JSON string
- get(key): retrieves and parses JSON, returns None if missing
- set_city_state(city, state_dict): stores FSM state + visit score
- get_city_state(city): retrieves city state dict
- get_all_city_states(): returns all 8 cities current states

STEP 9 — dags/sensor_pipeline_dag.py
Airflow DAG:
- dag_id: citypulse_sensor_pipeline
- schedule: */5 * * * * (every 5 minutes)
- default_args: retries=2, retry_delay=30s
- Tasks in sequence:
  1. fetch_and_publish: runs producer.run_once()
  2. consume_and_store: runs consumer for 60 seconds
  3. log_pipeline_health: logs row counts to Airflow logs
- Load all credentials from environment variables
- Copy this DAG file to the Docker Airflow dags folder:
  docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/

STEP 10 — requirements.txt
confluent-kafka==2.3.0
supabase==2.3.0
requests==2.31.0
python-dotenv==1.0.0
pandas==2.1.0
numpy==1.26.0
pytest==7.4.0
apache-airflow==2.8.0

STEP 11 — .gitignore
Add: .env, __pycache__, *.pyc, .pytest_cache, *.pt, *.pkl

STEP 12 — Run and validate in this exact order:
1. pip install -r requirements.txt
2. python database/supabase_client.py --migrate
   Confirm: "Tables created successfully"
3. python kafka/producer.py
   Confirm: "Published 8 sensor readings to Kafka"
4. python kafka/consumer.py --duration 30
   Confirm: "Consumed X messages, wrote to Supabase and Redis"
5. python database/redis_client.py --test
   Confirm: "All 8 city states found in Redis"
6. docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
   Then check localhost:8080 — DAG should appear
7. pytest tests/ -v
   Confirm: all tests pass
8. Print final status:
   "Day 1 complete.
    Supabase: X sensor readings inserted
    Redis: 8 city states cached
    Airflow DAG: citypulse_sensor_pipeline active
    Kafka pipeline: healthy"

Load ALL credentials from .env using python-dotenv.
Type hints on all functions and classes.
Docstrings on all public methods.
Never hardcode any credential anywhere.
Handle all API errors gracefully — a single city failure must 
never crash the entire pipeline.
Print clear progress messages as each step completes.