"""
producer.py — Kafka producer for CityPulse sensor data using Redpanda (SASL_SSL + SCRAM-SHA-256).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from confluent_kafka import Producer, KafkaException
from dotenv import load_dotenv

# Allow running as a script from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.cities_config import CITY_NAMES
from data.fetch_weather import FetchWeather
from data.fetch_airquality import FetchAirQuality

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class SensorDataProducer:
    """Publishes sensor readings for all Swiss cities to a Kafka topic."""

    def __init__(self) -> None:
        """Initialises the Kafka producer from environment variables."""
        self.topic: str = os.environ["KAFKA_TOPIC_SENSOR"]
        config: Dict[str, Any] = {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "security.protocol": "SASL_SSL",
            "sasl.mechanism": "SCRAM-SHA-256",
            "sasl.username": os.environ["KAFKA_API_KEY"],
            "sasl.password": os.environ["KAFKA_API_SECRET"],
        }
        self.producer = Producer(config)
        self.weather_fetcher = FetchWeather()
        self.aq_fetcher = FetchAirQuality()

    def _delivery_callback(self, err: Optional[Exception], msg: Any) -> None:
        """Kafka delivery report callback — logs success or failure.

        Args:
            err: Delivery error, or None on success.
            msg: The delivered message object.
        """
        if err:
            logger.error("Delivery failed for city message: %s", err)
        else:
            logger.info(
                "Delivered to %s [partition %d] offset %d",
                msg.topic(), msg.partition(), msg.offset(),
            )

    def publish_sensor_reading(
        self,
        city: str,
        weather_data: Dict[str, Any],
        aq_data: Dict[str, Any],
    ) -> None:
        """Publishes a combined sensor reading for one city to Kafka.

        Args:
            city: City name.
            weather_data: Dict with temperature_c, humidity_pct, wind_speed_kmh, precipitation_mm.
            aq_data: Dict with pm25, pm10.
        """
        payload = {
            "city": city,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **weather_data,
            **aq_data,
            "crowd_index": None,  # Reserved for future crowd data integration
        }
        self.producer.produce(
            self.topic,
            key=city.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
            callback=self._delivery_callback,
        )
        self.producer.poll(0)

    def run_once(self) -> int:
        """Fetches all 8 cities and publishes a sensor reading for each.

        Returns:
            Number of readings successfully published.
        """
        published = 0
        for city in CITY_NAMES:
            try:
                weather = self.weather_fetcher.fetch_current(city)
                aq = self.aq_fetcher.fetch_current(city)

                if weather is None:
                    logger.warning("[%s] Skipping — weather fetch failed", city)
                    continue

                self.publish_sensor_reading(city, weather, aq)
                published += 1
                logger.info("[%s] Reading queued for publish", city)
            except Exception as e:
                logger.error("[%s] Unexpected error: %s", city, e)

        self.producer.flush()
        logger.info("Published %d sensor readings to Kafka", published)
        return published


if __name__ == "__main__":
    producer = SensorDataProducer()
    count = producer.run_once()
    print(f"Published {count} sensor readings to Kafka")
