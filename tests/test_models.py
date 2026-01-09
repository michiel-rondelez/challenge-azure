"""Unit tests for data models"""
import pytest
from datetime import datetime
from shared.models import Station, Departure


class TestStation:
    """Tests for Station model"""

    def test_station_creation(self):
        """Test creating a station"""
        station = Station(
            id=1,
            name="Brussels-Central",
            standard_name="Brussel-Centraal"
        )
        assert station.id == 1
        assert station.name == "Brussels-Central"
        assert station.standard_name == "Brussel-Centraal"

    def test_station_from_api(self):
        """Test creating station from API data"""
        api_data = {
            "id": "BE.NMBS.008813003",
            "name": "Brussels-Central/Brussel-Centraal",
            "standardname": "Brussel-Centraal",
            "locationX": "4.357487",
            "locationY": "50.845466"
        }

        station = Station.from_api(api_data)

        assert station.name == "Brussels-Central/Brussel-Centraal"
        assert station.standard_name == "Brussel-Centraal"
        assert station.irail_id == "BE.NMBS.008813003"
        assert station.location_x == "4.357487"
        assert station.location_y == "50.845466"

    def test_station_from_db_row(self):
        """Test creating station from database row"""
        db_row = (
            1,  # id
            "Brussels-Central",  # name
            "Brussel-Centraal",  # standard_name
            4.357487,  # location_x
            50.845466,  # location_y
            "BE.NMBS.008813003",  # irail_id
            datetime(2024, 1, 1, 12, 0, 0)  # created_at
        )

        station = Station.from_db_row(db_row)

        assert station.id == 1
        assert station.name == "Brussels-Central"
        assert station.created_at == datetime(2024, 1, 1, 12, 0, 0)


class TestDeparture:
    """Tests for Departure model"""

    def test_departure_creation(self):
        """Test creating a departure"""
        departure = Departure(
            id=1,
            station_id=5,
            train_id="BE.NMBS.IC1832",
            vehicle="IC1832",
            platform="3",
            delay=180,
            direction="Oostende"
        )

        assert departure.id == 1
        assert departure.station_id == 5
        assert departure.delay == 180

    def test_departure_from_api(self):
        """Test creating departure from API data"""
        api_data = {
            "id": "1",
            "vehicle": "BE.NMBS.IC1832",
            "platform": "3",
            "time": "1704106800",  # Unix timestamp
            "delay": "180",
            "station": "Oostende"
        }

        departure = Departure.from_api(api_data, station_id=5)

        assert departure.station_id == 5
        assert departure.train_id == "1"
        assert departure.vehicle == "BE.NMBS.IC1832"
        assert departure.platform == "3"
        assert departure.delay == 180
        assert departure.direction == "Oostende"
        assert departure.fetched_at is not None

    def test_departure_from_api_missing_delay(self):
        """Test creating departure when delay is missing"""
        api_data = {
            "id": "1",
            "vehicle": "BE.NMBS.IC1832",
            "platform": "3",
            "time": "1704106800",
            "station": "Oostende"
        }

        departure = Departure.from_api(api_data, station_id=5)

        assert departure.delay == 0  # Default value

    def test_departure_from_db_row(self):
        """Test creating departure from database row"""
        db_row = (
            1,  # id
            5,  # station_id
            "BE.NMBS.IC1832",  # train_id
            "IC1832",  # vehicle
            "3",  # platform
            datetime(2024, 1, 1, 14, 30, 0),  # scheduled_time
            180,  # delay
            "Oostende",  # direction
            datetime(2024, 1, 1, 14, 25, 0)  # fetched_at
        )

        departure = Departure.from_db_row(db_row)

        assert departure.id == 1
        assert departure.station_id == 5
        assert departure.delay == 180
        assert departure.direction == "Oostende"
