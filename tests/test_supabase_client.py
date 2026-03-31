"""
test_supabase_client.py — Unit tests for SupabaseClient using mocked Supabase responses.
"""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")


def make_mock_response(data: list, count: int = None) -> MagicMock:
    """Creates a mock Supabase response object."""
    mock = MagicMock()
    mock.data = data
    mock.count = count
    return mock


@pytest.fixture
def db():
    with patch("database.supabase_client.create_client") as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        from database.supabase_client import SupabaseClient
        client = SupabaseClient()
        client.client = mock_client
        return client


class TestInsertSensorReading:
    def test_insert_called_with_city(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = make_mock_response([])

        db.insert_sensor_reading("Zurich", {"temperature_c": 12.0})
        db.client.table.assert_called_with("sensor_readings")

    def test_insert_does_not_raise_on_error(self, db) -> None:
        db.client.table.side_effect = Exception("DB error")
        # Should log error and not raise
        db.insert_sensor_reading("Geneva", {"temperature_c": 10.0})


class TestInsertAnomalyScore:
    def test_insert_called_with_correct_table(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = make_mock_response([])

        db.insert_anomaly_score("Bern", {"anomaly_score": 0.75, "fsm_state": "ALERT", "visit_score": 3})
        db.client.table.assert_called_with("anomaly_scores")


class TestGetLatestScores:
    def test_returns_dataframe(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        mock_table.select.return_value.gte.return_value.order.return_value.execute.return_value = make_mock_response(
            [{"city": "Zurich", "anomaly_score": 0.5}]
        )
        result = db.get_latest_scores(hours=24)
        assert isinstance(result, pd.DataFrame)

    def test_returns_empty_df_on_error(self, db) -> None:
        db.client.table.side_effect = Exception("DB error")
        result = db.get_latest_scores()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestGetCityLatest:
    def test_returns_dict_on_success(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        row = {"city": "Basel", "anomaly_score": 0.3}
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = make_mock_response([row])

        result = db.get_city_latest("Basel")
        assert result == row

    def test_returns_none_when_no_data(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = make_mock_response([])

        result = db.get_city_latest("Zermatt")
        assert result is None


class TestGetRecentReadings:
    def test_returns_dataframe(self, db) -> None:
        mock_table = MagicMock()
        db.client.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = make_mock_response(
            [{"city": "Lucerne", "temperature_c": 9.0}]
        )
        result = db.get_recent_readings("Lucerne", limit=10)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
