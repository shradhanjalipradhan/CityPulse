"""
sensor_pipeline_dag.py — Apache Airflow DAG for the CityPulse sensor data pipeline.
Runs every 5 minutes: fetch → publish → consume → health log.

Deploy to Docker Airflow with:
    docker cp dags/sensor_pipeline_dag.py airflow:/opt/airflow/dags/
"""

import logging
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/opt/airflow/citypulse')

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "citypulse",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "email_on_failure": False,
    "email_on_retry": False,
}


def fetch_and_publish() -> None:
    """Task 1 — Fetches sensor data for all 8 cities and publishes to Kafka."""
    from kafka.producer import SensorDataProducer

    producer = SensorDataProducer()
    count = producer.run_once()
    logger.info("fetch_and_publish: published %d readings", count)
    if count == 0:
        raise RuntimeError("No sensor readings were published — aborting pipeline run")


def consume_and_store() -> None:
    """Task 2 — Consumes from Kafka for 60 seconds and writes to Supabase + Redis."""
    from kafka.consumer import SensorDataConsumer

    consumer = SensorDataConsumer()
    consumed = consumer.run(duration_seconds=60)
    logger.info("consume_and_store: consumed %d messages", consumed)


def run_inference() -> None:
    """Task 3 — Reads latest Supabase windows, calls HF /predict, writes anomaly scores."""
    from models.inference_engine import InferenceEngine

    engine = InferenceEngine()
    results = engine.run_all_cities()
    success = sum(1 for v in results.values() if v is not None)
    logger.info("run_inference: completed %d / %d cities", success, len(results))


def log_pipeline_health() -> None:
    """Task 3 — Logs Supabase row counts and Redis city state counts to Airflow logs."""
    from database.supabase_client import SupabaseClient
    from database.redis_client import RedisClient

    db = SupabaseClient()
    redis = RedisClient()

    try:
        sensor_resp = db.client.table("sensor_readings").select("id", count="exact").execute()
        sensor_count = sensor_resp.count if hasattr(sensor_resp, "count") else len(sensor_resp.data)
    except Exception as e:
        sensor_count = f"error: {e}"

    try:
        anomaly_resp = db.client.table("anomaly_scores").select("id", count="exact").execute()
        anomaly_count = anomaly_resp.count if hasattr(anomaly_resp, "count") else len(anomaly_resp.data)
    except Exception as e:
        anomaly_count = f"error: {e}"

    states = redis.get_all_city_states()
    cached_cities = sum(1 for v in states.values() if v is not None)

    logger.info(
        "Pipeline health — sensor_readings: %s | anomaly_scores: %s | Redis city states: %d/8",
        sensor_count,
        anomaly_count,
        cached_cities,
    )


with DAG(
    dag_id="citypulse_sensor_pipeline",
    default_args=DEFAULT_ARGS,
    description="CityPulse Switzerland — real-time sensor ingestion pipeline",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["citypulse", "sensors", "switzerland"],
) as dag:

    t1 = PythonOperator(
        task_id="fetch_and_publish",
        python_callable=fetch_and_publish,
    )

    t2 = PythonOperator(
        task_id="consume_and_store",
        python_callable=consume_and_store,
    )

    t3 = PythonOperator(
        task_id="run_inference",
        python_callable=run_inference,
    )

    t4 = PythonOperator(
        task_id="log_pipeline_health",
        python_callable=log_pipeline_health,
    )

    t1 >> t2 >> t3 >> t4
