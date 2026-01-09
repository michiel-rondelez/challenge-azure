import azure.functions as func
import logging
import os
import asyncio

# Import shared modules
from shared.db import get_db_connection, StationRepository, DepartureRepository
from shared.irail_client import IRailClient
from shared.models import Departure

# Early debugpy setup (before any other code) — only in DEBUG mode
if os.environ.get("DEBUG") == "1":
    try:
        import debugpy
        import socket

        def _is_port_free(port, host="0.0.0.0"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((host, port))
                    return True
                except OSError:
                    return False

        ports_to_try = []
        if os.environ.get("DEBUG_PORT"):
            try:
                ports_to_try.append(int(os.environ.get("DEBUG_PORT")))
            except ValueError:
                logging.warning("DEBUG_PORT is not an integer; falling back to default ports")

        ports_to_try.extend(range(5678, 5688))  # try a small range

        debug_port_chosen = None
        for p in ports_to_try:
            if not _is_port_free(p):
                continue
            try:
                debugpy.listen(("0.0.0.0", p))
                debug_port_chosen = p
                logging.info(f"Debugpy listening on port {p}")
                break
            except Exception as e:
                logging.warning(f"debugpy.listen failed on port {p}: {e}")
                continue

        if not debug_port_chosen:
            logging.info("Debugging not started — no free debug port available or debugpy failed")

    except ImportError:
        logging.warning("debugpy not installed; debugging disabled")
    except Exception as e:
        logging.warning(f"Unexpected error setting up debugpy: {e}")

# NEW: log chosen Functions host port if set by runner
FUNCTIONS_PORT = os.environ.get("FUNCTIONS_PORT") or os.environ.get("FUNC_PORT")
if FUNCTIONS_PORT:
    logging.info(f"Functions host expected to run on port {FUNCTIONS_PORT}")

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
        logging.info("Starting to fetch stations from iRail API...")

        # Fetch all stations using the client
        stations = irail_client.fetch_all_stations()
        if not stations:
            logging.warning("No stations returned from API")
            return 0

        logging.info(f"Successfully fetched {len(stations)} stations from iRail API")

        conn = get_db_connection()
        cursor = conn.cursor()

        inserted_count = 0
        updated_count = 0

        for station in stations:
            # Check if station exists
            cursor.execute("SELECT id FROM Stations WHERE name = ?", (station.name,))
            existing = cursor.fetchone()

            if existing:
                logging.debug(f"Updating existing station: {station.name}")
                updated_count += 1
            else:
                logging.info(f"Inserting new station: {station.name} (standardname: {station.standard_name})")
                inserted_count += 1

            StationRepository.upsert(cursor, station)

        conn.commit()
        conn.close()

        logging.info(f"Stations sync completed: {inserted_count} new stations inserted, {updated_count} existing stations updated")
        return inserted_count + updated_count

    except Exception as e:
        logging.error(f"Error fetching stations: {str(e)}")
        return 0

# --- Liveboard Fetching Logic ---
async def fetch_and_store_all_liveboards_async():
    """Fetch liveboard data for all stations concurrently using async"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all stations from database
        stations = StationRepository.get_all(cursor)

        if not stations:
            logging.warning("No stations found in database")
            conn.close()
            return 0

        # Prepare station list for async fetching
        station_list = [(s.id, s.standard_name or s.name) for s in stations]

        logging.info(f"Fetching liveboards for {len(station_list)} stations concurrently...")

        # Fetch all liveboards concurrently (max 5 concurrent requests to respect API limits)
        results = await irail_client.fetch_multiple_liveboards_async(station_list, max_concurrent=5)

        total_departures = 0

        # Process results and insert into database
        for station_id, departures_data in results.items():
            if departures_data:
                try:
                    departures = [Departure.from_api(dep, station_id) for dep in departures_data]
                    count = DepartureRepository.insert_batch(cursor, departures)
                    total_departures += count
                except Exception as e:
                    logging.error(f"Error processing departures for station {station_id}: {str(e)}")
                    continue

        conn.commit()
        conn.close()

        logging.info(f"Successfully inserted {total_departures} departures from {len(results)} stations")
        return total_departures

    except Exception as e:
        logging.error(f"Error in fetch_and_store_all_liveboards_async: {str(e)}")
        return 0

def fetch_and_store_all_liveboards():
    """Synchronous wrapper for async liveboard fetching"""
    return asyncio.run(fetch_and_store_all_liveboards_async())

# --- Triggers ---
@app.route(route="fetch_trains", auth_level=func.AuthLevel.FUNCTION)
def fetch_trains_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info(f"HTTP trigger: {req.method} {req.url}")
    logging.info(f"Query params: {dict(req.params)}")

    station = req.params.get('station', 'Brussels-Central')
    count = fetch_and_store_trains(station)
    return func.HttpResponse(f"Inserted {count} records for {station}", status_code=200 if count > 0 else 500)

@app.route(route="ingest_departures", auth_level=func.AuthLevel.FUNCTION)
def ingest_departures_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger to fetch and store departures for a specific station (same as fetch_trains)"""
    logging.info(f"HTTP trigger: {req.method} {req.url}")
    logging.info(f"Query params: {dict(req.params)}")

    station = req.params.get('station', 'Brussels-Central')
    count = fetch_and_store_trains(station)
    return func.HttpResponse(f"Inserted {count} departure records for {station}", status_code=200 if count > 0 else 500)

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

# --- New scheduled wrapper for stations ingestion ---
@app.schedule(schedule="0 0 * * * *", arg_name="mytimer")
def ingest_stations_scheduled(mytimer: func.TimerRequest) -> None:
    """Scheduled trigger to ingest all stations (runs daily at top of hour)"""
    logging.info(f"Timer trigger (ingest_stations) fired. Past due: {mytimer.past_due}")
    fetch_and_store_all_stations()