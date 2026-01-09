"""iRail API client for fetching train data"""
import requests
import logging
import time
import asyncio
import aiohttp
from typing import List, Dict, Optional
from .models import Station, Departure


class IRailClient:
    """Client for interacting with the iRail API"""

    BASE_URL = "https://api.irail.be/"
    USER_AGENT = "AzureTrainData/1.0 (becode.org; michiel.rondelez.pro@gmail.com)"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def _make_request(self, endpoint: str, params: dict, max_retries: int = 3) -> Optional[dict]:
        """Make HTTP request to iRail API with exponential backoff retry"""
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{self.BASE_URL}{endpoint}",
                    params=params,
                    headers={"User-Agent": self.USER_AGENT},
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limited
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        logging.warning(f"Rate limited (429), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                logging.error(f"iRail API request failed: {str(e)}")
                return None
            except requests.exceptions.RequestException as e:
                logging.error(f"iRail API request failed: {str(e)}")
                return None

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

    async def fetch_liveboard_async(self, session: aiohttp.ClientSession, station_name: str, semaphore: asyncio.Semaphore, max_retries: int = 3) -> Optional[List[Dict]]:
        """Async fetch liveboard with rate limiting via semaphore"""
        async with semaphore:  # Limit concurrent requests
            for attempt in range(max_retries):
                try:
                    async with session.get(
                        f"{self.BASE_URL}liveboard/",
                        params={"station": station_name, "format": "json", "fast": "true"},
                        headers={"User-Agent": self.USER_AGENT},
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as response:
                        if response.status == 429:  # Rate limited
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt) * 2
                                logging.warning(f"Rate limited (429) for {station_name}, retrying in {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            logging.error(f"Rate limit exceeded for {station_name} after {max_retries} retries")
                            return None

                        response.raise_for_status()
                        data = await response.json()
                        departures_data = data.get("departures", {})
                        return departures_data.get("departure", [])

                except aiohttp.ClientError as e:
                    logging.error(f"Async request failed for {station_name}: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    return None

            return None

    async def fetch_multiple_liveboards_async(self, stations: List[tuple], max_concurrent: int = 5) -> Dict[int, List[Dict]]:
        """
        Fetch liveboards for multiple stations concurrently with rate limiting

        Args:
            stations: List of (station_id, station_name) tuples
            max_concurrent: Maximum number of concurrent requests (default: 5 to respect API limits)

        Returns:
            Dict mapping station_id to list of departure data
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}

        async with aiohttp.ClientSession() as session:
            tasks = []
            for station_id, station_name in stations:
                task = self._fetch_with_id(session, station_id, station_name, semaphore)
                tasks.append(task)

            # Wait for all tasks to complete
            completed = await asyncio.gather(*tasks, return_exceptions=True)

            for station_id, departures in completed:
                if not isinstance(station_id, Exception) and departures:
                    results[station_id] = departures

        return results

    async def _fetch_with_id(self, session: aiohttp.ClientSession, station_id: int, station_name: str, semaphore: asyncio.Semaphore) -> tuple:
        """Helper to fetch and return with station_id"""
        departures = await self.fetch_liveboard_async(session, station_name, semaphore)
        return (station_id, departures)
