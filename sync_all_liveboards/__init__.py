"""Timer and HTTP trigger function to sync liveboards for all stations"""
import azure.functions as func
import logging
import time
import sys
import os

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.irail_client import IRailClient
from shared.db import get_db_connection, StationRepository, DepartureRepository
from shared.models import Departure


def sync_all_liveboards() -> tuple[int, int]:
    """
    Sync liveboards for all stations in the database.

    Returns:
        tuple: (total_departures_inserted, total_stations_processed)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all stations
    stations = StationRepository.get_all(cursor)

    if not stations:
        logging.warning("No stations found in database")
        conn.close()
        return 0, 0

    client = IRailClient()
    total_departures = 0
    stations_processed = 0

    for station in stations:
        # Use standard_name for API call, fallback to name
        api_station_name = station.standard_name or station.name

        try:
            # Fetch liveboard for this station
            departures_data = client.fetch_liveboard(api_station_name)

            if departures_data:
                departures = [Departure.from_api(dep_data, station.id)
                            for dep_data in departures_data]
                count = DepartureRepository.insert_batch(cursor, departures)
                total_departures += count
                logging.info(f"Inserted {count} departures for {station.name}")

            stations_processed += 1

            # Respect API rate limits
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"Error fetching liveboard for {station.name}: {str(e)}")
            continue

    conn.commit()
    conn.close()

    logging.info(f"Successfully inserted {total_departures} departures from {stations_processed} stations")
    return total_departures, stations_processed


def main(req: func.HttpRequest = None, mytimer: func.TimerRequest = None) -> func.HttpResponse:
    """
    Dual-purpose function that can be triggered by:
    1. HTTP request: GET /api/sync_all_liveboards
    2. Timer: Every 15 minutes (0 */15 * * * *)

    Returns: Count of departure records inserted and stations processed
    """
    if mytimer:
        logging.info('Timer trigger: Starting scheduled liveboard sync')
    else:
        logging.info('HTTP trigger: Starting manual liveboard sync')

    try:
        total_departures, stations_processed = sync_all_liveboards()

        message = f"Successfully inserted {total_departures} departure records from {stations_processed} stations"
        logging.info(message)

        # HTTP response (ignored for timer trigger)
        if req:
            return func.HttpResponse(message, status_code=200)

    except Exception as e:
        error_msg = f"Error syncing liveboards: {str(e)}"
        logging.error(error_msg)

        if req:
            return func.HttpResponse(error_msg, status_code=500)
