"""HTTP trigger function to fetch and store all train stations"""
import azure.functions as func
import logging
import sys
import os

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.irail_client import IRailClient
from shared.db import get_db_connection, StationRepository


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger to fetch all stations from iRail API and store them in the database.

    GET /api/ingest_stations

    Returns: Count of stations processed (inserted + updated)
    """
    logging.info('Starting station ingestion')

    try:
        # Fetch stations from API
        client = IRailClient()
        stations = client.fetch_all_stations()

        if not stations:
            logging.warning("No stations returned from API")
            return func.HttpResponse(
                "No stations found",
                status_code=404
            )

        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()

        inserted_count = 0
        updated_count = 0

        for station in stations:
            # Check if station exists to determine if insert or update
            cursor.execute("SELECT id FROM Stations WHERE name = ?", (station.name,))
            existing = cursor.fetchone()

            if existing:
                updated_count += 1
            else:
                inserted_count += 1

            StationRepository.upsert(cursor, station)

        conn.commit()
        conn.close()

        message = f"Stations sync complete: {inserted_count} new, {updated_count} updated (total: {len(stations)})"
        logging.info(message)

        return func.HttpResponse(
            message,
            status_code=200
        )

    except Exception as e:
        error_msg = f"Error ingesting stations: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(
            error_msg,
            status_code=500
        )
