-- CityPulse Switzerland — Database Migrations
-- Run this once against your Supabase project via the SQL editor or supabase_client.py --migrate

-- Table: sensor_readings
-- Stores raw weather + air quality readings fetched from OpenMeteo and OpenAQ
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

-- Table: anomaly_scores
-- Stores computed anomaly scores and FSM state per city per pipeline run
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

-- Table: alert_events
-- Stores FSM state transition events (e.g. NORMAL -> ALERT)
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

-- Indexes for fast time-series queries per city
CREATE INDEX IF NOT EXISTS idx_sensor_city_time
  ON sensor_readings (city, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_city_time
  ON anomaly_scores (city, timestamp DESC);
