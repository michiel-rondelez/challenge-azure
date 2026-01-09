"""iRail API client for fetching train data"""
import requests
import logging
from typing import List, Dict, Optional
from .models import Station, Departure


class IRailClient:
    """Client for interacting with the iRail API"""

    BASE_URL = "https://api.irail.be/"
    USER_AGENT = "AzureTrainData/1.0 (becode.org; michiel.rondelez.pro@gmail.com)"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make HTTP request to iRail API"""
        try:
            response = requests.get(
                f"{self.BASE_URL}{endpoint}",
                params=params,
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"iRail API request failed: {str(e)}")
            return None

    def fetch_all_stations(self) -> List[Station]:
        """Fetch all stations from iRail API"""
        data = self._make_request("stations/", {
            "format": "json",
            "lang": "en"
        })

        if not data:
            return []

        stations_data = data.get("station", [])
        return [Station.from_api(station_data) for station_data in stations_data]

    def fetch_liveboard(self, station_name: str) -> List[Dict]:
        """Fetch liveboard (departures) for a specific station"""
        data = self._make_request("liveboard/", {
            "station": station_name,
            "format": "json",
            "fast": "true"
        })

        if not data:
            return []

        departures_data = data.get("departures", {})
        return departures_data.get("departure", [])

    def fetch_liveboard_as_models(self, station_name: str, station_id: int) -> List[Departure]:
        """Fetch liveboard and convert to Departure models"""
        departures_data = self.fetch_liveboard(station_name)
        return [Departure.from_api(dep_data, station_id) for dep_data in departures_data]
