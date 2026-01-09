import azure.functions as func
import logging
import os
import time

# Import shared modules
from shared.db import get_db_connection, StationRepository, DepartureRepository
from shared.irail_client import IRailClient
from shared.models import Departure

# Early debugpy setup (before any other code) — only in DEBUG mode
if os.environ.get("DEBUG") == "1":
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", 5678))
        logging.info("Debugpy listening on port 5678")
    except ImportError:
        logging.warning("debugpy not installed; debugging disabled")

app = func.FunctionApp()

# --- Configuration ---
irail_client = IRailClient()

# --- Main Logic ---
def fetch_and_store_trains(station="Brussels-Central"):
    try:
        # Fetch liveboard data
        departures_data = irail_client.fetch_liveboard(station)
        if not departures_data:
            return 0

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get or create station
        station_id = StationRepository.get_or_create_simple(cursor, station)

        # Convert to Departure models and insert
        departures = [Departure.from_api(dep, station_id) for dep in departures_data]
        inserted_count = DepartureRepository.insert_batch(cursor, departures)

        conn.commit()
        conn.close()

        logging.info(f"Successfully inserted {inserted_count} records for {station}")
        return inserted_count

    except Exception as e:
        logging.error(f"Error for {station}: {str(e)}")
        return 0

# --- Stations Fetching Logic ---
def fetch_and_store_all_stations():
    """Fetch all stations from iRail API and store them in the database"""
    try:
        # Fetch all stations using the client
        stations = irail_client.fetch_all_stations()
        if not stations:
            logging.warning("No stations returned from API")
            return 0

        conn = get_db_connection()
        cursor = conn.cursor()

        inserted_count = 0
        updated_count = 0

        for station in stations:
            # Check if station exists
            cursor.execute("SELECT id FROM Stations WHERE name = ?", (station.name,))
            existing = cursor.fetchone()

            if existing:
                updated_count += 1
            else:
                inserted_count += 1

            StationRepository.upsert(cursor, station)

        conn.commit()
        conn.close()

        logging.info(f"Stations sync: {inserted_count} new, {updated_count} updated")
        return inserted_count + updated_count

    except Exception as e:
        logging.error(f"Error fetching stations: {str(e)}")
        return 0

# --- Liveboard Fetching Logic ---
def fetch_and_store_all_liveboards():
    """Fetch liveboard data for all stations in the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all stations from database
        stations = StationRepository.get_all(cursor)

        if not stations:
            logging.warning("No stations found in database")
            conn.close()
            return 0

        total_departures = 0

        for station in stations:
            # Use standard_name for API call, fallback to name
            api_station_name = station.standard_name or station.name

            try:
                # Fetch liveboard for this station
                departures_data = irail_client.fetch_liveboard(api_station_name)

                if departures_data:
                    departures = [Departure.from_api(dep, station.id) for dep in departures_data]
                    count = DepartureRepository.insert_batch(cursor, departures)
                    total_departures += count

                # Respect API rate limits
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error fetching liveboard for {station.name}: {str(e)}")
                continue

        conn.commit()
        conn.close()

        logging.info(f"Successfully inserted {total_departures} departures from {len(stations)} stations")
        return total_departures

    except Exception as e:
        logging.error(f"Error in fetch_and_store_all_liveboards: {str(e)}")
        return 0

# --- Triggers ---
@app.route(route="fetch_trains", auth_level=func.AuthLevel.FUNCTION)
def fetch_trains_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info(f"HTTP trigger: {req.method} {req.url}")
    logging.info(f"Query params: {dict(req.params)}")

    station = req.params.get('station', 'Brussels-Central')
    count = fetch_and_store_trains(station)
    return func.HttpResponse(f"Inserted {count} records for {station}", status_code=200 if count > 0 else 500)

@app.schedule(schedule="0 0 * * * *", arg_name="mytimer")
def fetch_trains_scheduled(mytimer: func.TimerRequest) -> None:
    logging.info(f"Timer trigger fired. Past due: {mytimer.past_due}")

    for station in ["Brussels-Central", "Antwerp-Central", "Ghent-Sint-Pieters"]:
        fetch_and_store_trains(station)
        time.sleep(1) # Respect API limits

# --- New Stations Triggers ---
@app.route(route="fetch_stations", auth_level=func.AuthLevel.FUNCTION)
def fetch_stations_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger to fetch and store all stations"""
    logging.info(f"HTTP trigger: {req.method} {req.url}")
    logging.info(f"Query params: {dict(req.params)}")

    count = fetch_and_store_all_stations()
    return func.HttpResponse(
        f"Successfully processed {count} stations",
        status_code=200 if count > 0 else 500
    )

# --- New Liveboard Triggers ---
@app.route(route="fetch_all_liveboards", auth_level=func.AuthLevel.FUNCTION)
def fetch_all_liveboards_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger to fetch liveboard data for all stations"""
    logging.info(f"HTTP trigger: {req.method} {req.url}")
    logging.info(f"Query params: {dict(req.params)}")

    count = fetch_and_store_all_liveboards()
    return func.HttpResponse(
        f"Successfully inserted {count} departure records",
        status_code=200 if count > 0 else 500
    )

@app.schedule(schedule="0 */15 * * * *", arg_name="mytimer")
def fetch_all_liveboards_scheduled(mytimer: func.TimerRequest) -> None:
    """Schedule trigger to fetch all liveboards every 15 minutes"""
    logging.info(f"Timer trigger fired. Past due: {mytimer.past_due}")

    fetch_and_store_all_liveboards()