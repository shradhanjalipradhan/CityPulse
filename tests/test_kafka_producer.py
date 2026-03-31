"""
test_kafka_producer.py — Unit tests for SensorDataProducer using mocked Kafka and fetchers.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# Set dummy env vars before importing the producer so dotenv doesn't block tests
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "test-broker:9092")
os.environ.setdefault("KAFKA_API_KEY", "test-key")
os.environ.setdefault("KAFKA_API_SECRET", "test-secret")
os.environ.setdefault("KAFKA_TOPIC_SENSOR", "test-topic")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://test.upstash.io")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test-token")

MOCK_WEATHER = {
    "temperature_c": 14.0,
    "humidity_pct": 65.0,
    "wind_speed_kmh": 20.0,
    "precipitation_mm": 0.0,
}

MOCK_AQ = {"pm25": 8.0, "pm10": 15.0}


@pytest.fixture
def producer():
    with patch("confluent_kafka.Producer") as MockProducer:
        mock_instance = MagicMock()
        MockProducer.return_value = mock_instance
        from kafka.producer import SensorDataProducer
        p = SensorDataProducer()
        p.producer = mock_instance
        return p


class TestPublishSensorReading:
    def test_produce_called_once(self, producer) -> None:
        producer.publish_sensor_reading("Zurich", MOCK_WEATHER, MOCK_AQ)
        producer.producer.produce.assert_called_once()

    def test_produce_uses_correct_topic(self, producer) -> None:
        producer.publish_sensor_reading("Geneva", MOCK_WEATHER, MOCK_AQ)
        call_kwargs = producer.producer.produce.call_args
        assert call_kwargs[0][0] == "test-topic"

    def test_produce_uses_city_as_key(self, producer) -> None:
        producer.publish_sensor_reading("Bern", MOCK_WEATHER, MOCK_AQ)
        call_kwargs = producer.producer.produce.call_args
        assert call_kwargs[1]["key"] == b"Bern"

    def test_payload_contains_city(self, producer) -> None:
        import json
        producer.publish_sensor_reading("Basel", MOCK_WEATHER, MOCK_AQ)
        call_kwargs = producer.producer.produce.call_args
        payload = json.loads(call_kwargs[1]["value"].decode())
        assert payload["city"] == "Basel"

    def test_payload_contains_all_sensor_fields(self, producer) -> None:
        import json
        producer.publish_sensor_reading("Lausanne", MOCK_WEATHER, MOCK_AQ)
        call_kwargs = producer.producer.produce.call_args
        payload = json.loads(call_kwargs[1]["value"].decode())
        for field in ["temperature_c", "humidity_pct", "wind_speed_kmh", "precipitation_mm", "pm25", "pm10"]:
            assert field in payload


class TestRunOnce:
    def test_publishes_8_cities(self, producer) -> None:
        with patch.object(producer.weather_fetcher, "fetch_current", return_value=MOCK_WEATHER), \
             patch.object(producer.aq_fetcher, "fetch_current", return_value=MOCK_AQ):
            count = producer.run_once()
        assert count == 8

    def test_skips_city_on_weather_failure(self, producer) -> None:
        with patch.object(producer.weather_fetcher, "fetch_current", return_value=None), \
             patch.object(producer.aq_fetcher, "fetch_current", return_value=MOCK_AQ):
            count = producer.run_once()
        assert count == 0

    def test_single_city_exception_does_not_crash(self, producer) -> None:
        call_count = 0

        def weather_side_effect(city):
            nonlocal call_count
            call_count += 1
            if city == "Zurich":
                raise Exception("forced error")
            return MOCK_WEATHER

        with patch.object(producer.weather_fetcher, "fetch_current", side_effect=weather_side_effect), \
             patch.object(producer.aq_fetcher, "fetch_current", return_value=MOCK_AQ):
            count = producer.run_once()
        # 7 cities should succeed despite Zurich failing
        assert count == 7
