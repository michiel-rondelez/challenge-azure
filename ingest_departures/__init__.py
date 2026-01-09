"""HTTP trigger function to fetch and store departures for a specific station"""
import azure.functions as func
import logging
import sys
import os

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.irail_client import IRailClient
from shared.db import get_db_connection, StationRepository, DepartureRepository
from shared.models import Departure


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger to fetch liveboard data for a specific station and store departures.

    GET /api/ingest_departures?station=Brussels-Central

    Query Parameters:
        station (optional): Station name (default: Brussels-Central)

    Returns: Count of departure records inserted
    """
    station_name = req.params.get('station', 'Brussels-Central')
    logging.info(f'Fetching departures for station: {station_name}')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get or create station in database
        station_id = StationRepository.get_or_create_simple(cursor, station_name)

        # Fetch liveboard from API
        client = IRailClient()
        departures_data = client.fetch_liveboard(station_name)

        if not departures_data:
            logging.warning(f"No departures found for {station_name}")
            conn.close()
            return func.HttpResponse(
                f"No departures found for {station_name}",
                status_code=200
            )

        # Convert to models and insert
        departures = [Departure.from_api(dep_data, station_id) for dep_data in departures_data]
        inserted_count = DepartureRepository.insert_batch(cursor, departures)

        conn.commit()
        conn.close()

        message = f"Inserted {inserted_count} departure records for {station_name}"
        logging.info(message)

        return func.HttpResponse(
            message,
            status_code=200
        )

    except Exception as e:
        error_msg = f"Error ingesting departures for {station_name}: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(
            error_msg,
            status_code=500
        )
