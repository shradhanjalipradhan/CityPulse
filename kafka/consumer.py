"""
consumer.py — Kafka consumer for CityPulse. Reads sensor readings and writes
to Supabase (sensor_readings table) and Upstash Redis (latest reading per city).
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict

from confluent_kafka import Consumer, KafkaError, KafkaException
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.supabase_client import SupabaseClient
from database.redis_client import RedisClient

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

REDIS_LATEST_TTL = 600  # seconds


class SensorDataConsumer:
    """Consumes sensor readings from Kafka and stores them in Supabase and Redis."""

    def __init__(self) -> None:
        """Initialises the Kafka consumer from environment variables."""
        self.topic: str = os.environ["KAFKA_TOPIC_SENSOR"]
        config: Dict[str, Any] = {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "security.protocol": "SASL_SSL",
            "sasl.mechanism": "SCRAM-SHA-256",
            "sasl.username": os.environ["KAFKA_API_KEY"],
            "sasl.password": os.environ["KAFKA_API_SECRET"],
            "group.id": "citypulse-consumer-group",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
        self.consumer = Consumer(config)
        self.supabase = SupabaseClient()
        self.redis = RedisClient()

    def _process_message(self, payload: Dict[str, Any]) -> None:
        """Processes a single sensor reading message.

        Writes to Supabase sensor_readings and caches the latest reading in Redis.

        Args:
            payload: Parsed JSON message dict from Kafka.
        """
        city = payload.get("city")
        if not city:
            logger.warning("Message missing 'city' field — skipping")
            return

        sensor_data = {
            "timestamp": payload.get("timestamp"),
            "temperature_c": payload.get("temperature_c"),
            "humidity_pct": payload.get("humidity_pct"),
            "wind_speed_kmh": payload.get("wind_speed_kmh"),
            "precipitation_mm": payload.get("precipitation_mm"),
            "pm25": payload.get("pm25"),
            "pm10": payload.get("pm10"),
            "crowd_index": payload.get("crowd_index"),
        }

        self.supabase.insert_sensor_reading(city, sensor_data)

        redis_key = f"city:{city}:latest_reading"
        self.redis.set(redis_key, payload, ttl_seconds=REDIS_LATEST_TTL)
        logger.info("[%s] Written to Supabase and cached in Redis", city)

    def run(self, duration_seconds: int = 60) -> int:
        """Consumes messages for a fixed duration, then exits cleanly.

        Args:
            duration_seconds: How long to consume before stopping (default 60s).

        Returns:
            Total number of messages consumed.
        """
        self.consumer.subscribe([self.topic])
        logger.info("Subscribed to topic '%s' — consuming for %ds", self.topic, duration_seconds)

        consumed = 0
        deadline = time.time() + duration_seconds

        try:
            while time.time() < deadline:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                    else:
                        logger.error("Kafka error: %s", msg.error())
                    continue

                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                    self._process_message(payload)
                    consumed += 1
                except (json.JSONDecodeError, Exception) as e:
                    logger.error("Failed to process message: %s", e)

        except KafkaException as e:
            logger.error("Fatal Kafka error: %s", e)
        finally:
            self.consumer.close()
            logger.info("Consumer closed. Total messages consumed: %d", consumed)

        print(f"Consumed {consumed} messages, wrote to Supabase and Redis")
        return consumed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Kafka Consumer")
    parser.add_argument("--duration", type=int, default=60, help="Seconds to consume (default 60)")
    args = parser.parse_args()

    consumer = SensorDataConsumer()
    consumer.run(duration_seconds=args.duration)
