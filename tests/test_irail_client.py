"""Unit tests for iRail API client"""
import pytest
from unittest.mock import Mock, patch
from shared.irail_client import IRailClient
from shared.models import Station, Departure


class TestIRailClient:
    """Tests for IRailClient"""

    def setup_method(self):
        """Setup test client"""
        self.client = IRailClient(timeout=5)

    def test_client_initialization(self):
        """Test client is initialized with correct config"""
        assert self.client.timeout == 5
        assert self.client.BASE_URL == "https://api.irail.be/"
        assert "AzureTrainData" in self.client.USER_AGENT

    @patch('shared.irail_client.requests.get')
    def test_fetch_all_stations_success(self, mock_get):
        """Test fetching all stations successfully"""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "station": [
                {
                    "id": "BE.NMBS.008813003",
                    "name": "Brussels-Central",
                    "standardname": "Brussel-Centraal",
                    "locationX": "4.357487",
                    "locationY": "50.845466"
                },
                {
                    "id": "BE.NMBS.008821006",
                    "name": "Antwerp-Central",
                    "standardname": "Antwerpen-Centraal",
                    "locationX": "4.421101",
                    "locationY": "51.217158"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Call method
        stations = self.client.fetch_all_stations()

        # Verify
        assert len(stations) == 2
        assert isinstance(stations[0], Station)
        assert stations[0].name == "Brussels-Central"
        assert stations[1].name == "Antwerp-Central"

        # Verify API was called correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "stations/" in args[0]
        assert kwargs['params']['format'] == 'json'

    @patch('shared.irail_client.requests.get')
    def test_fetch_all_stations_empty(self, mock_get):
        """Test fetching stations returns empty list when no stations"""
        mock_response = Mock()
        mock_response.json.return_value = {"station": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        stations = self.client.fetch_all_stations()

        assert stations == []

    @patch('shared.irail_client.requests.get')
    def test_fetch_all_stations_api_error(self, mock_get):
        """Test handling API error when fetching stations"""
        mock_get.side_effect = Exception("API Error")

        stations = self.client.fetch_all_stations()

        assert stations == []

    @patch('shared.irail_client.requests.get')
    def test_fetch_liveboard_success(self, mock_get):
        """Test fetching liveboard successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "departures": {
                "departure": [
                    {
                        "id": "1",
                        "vehicle": "BE.NMBS.IC1832",
                        "platform": "3",
                        "time": "1704106800",
                        "delay": "0",
                        "station": "Oostende"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        departures = self.client.fetch_liveboard("Brussels-Central")

        assert len(departures) == 1
        assert departures[0]["vehicle"] == "BE.NMBS.IC1832"

        # Verify API was called correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "liveboard/" in args[0]
        assert kwargs['params']['station'] == "Brussels-Central"
        assert kwargs['params']['fast'] == "true"

    @patch('shared.irail_client.requests.get')
    def test_fetch_liveboard_as_models(self, mock_get):
        """Test fetching liveboard as Departure models"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "departures": {
                "departure": [
                    {
                        "id": "1",
                        "vehicle": "BE.NMBS.IC1832",
                        "platform": "3",
                        "time": "1704106800",
                        "delay": "180",
                        "station": "Oostende"
                    },
                    {
                        "id": "2",
                        "vehicle": "BE.NMBS.IC2132",
                        "platform": "5",
                        "time": "1704107400",
                        "delay": "0",
                        "station": "Liège"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        departures = self.client.fetch_liveboard_as_models("Brussels-Central", station_id=5)

        assert len(departures) == 2
        assert isinstance(departures[0], Departure)
        assert departures[0].station_id == 5
        assert departures[0].delay == 180
        assert departures[1].delay == 0

    @patch('shared.irail_client.requests.get')
    def test_user_agent_header(self, mock_get):
        """Test that User-Agent header is set correctly"""
        mock_response = Mock()
        mock_response.json.return_value = {"station": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.client.fetch_all_stations()

        # Check that User-Agent header was sent
        args, kwargs = mock_get.call_args
        assert 'headers' in kwargs
        assert 'User-Agent' in kwargs['headers']
        assert 'AzureTrainData' in kwargs['headers']['User-Agent']

    @patch('shared.irail_client.requests.get')
    def test_timeout_is_applied(self, mock_get):
        """Test that timeout parameter is applied"""
        mock_response = Mock()
        mock_response.json.return_value = {"station": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = IRailClient(timeout=15)
        client.fetch_all_stations()

        # Check that timeout was passed to requests
        args, kwargs = mock_get.call_args
        assert kwargs['timeout'] == 15
