import azure.functions as func
import logging
import os
import time

from shared.db_sqlalchemy import (
    get_session,
    StationRepositorySQLAlchemy as StationRepository,
    DepartureRepositorySQLAlchemy as DepartureRepository
)
from shared.irail_client import IRailClient
from shared.models import Station, Departure

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

app = func.FunctionApp()

# --- Configuration ---
irail_client = IRailClient()

# --- Main Logic ---
def fetch_and_store_trains(station="Brussels-Central"):
    """Deprecated: Use fetch_and_store_all_liveboards instead"""
    try:
        # Fetch liveboard data
        departures_data = irail_client.fetch_liveboard(station)
        if not departures_data:
            return 0

        session = get_session()

        # Get or create station
        station_id = StationRepository.get_or_create_simple(session, station)

        # Convert to Departure models and insert
        departures = [Departure.from_api(dep, station_id) for dep in departures_data]
        inserted_count = len(departures)
        for dep in departures:
            DepartureRepository.insert(session, dep)

        session.commit()
        session.close()

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

        session = get_session()

        inserted_count = 0
        updated_count = 0

        for station in stations:
            # Check if station exists using SQLAlchemy
            existing = StationRepository.get_by_name(session, station.name)

            if existing:
                logging.debug(f"Updating existing station: {station.name}")
                updated_count += 1
            else:
                logging.info(f"Inserting new station: {station.name} (standardname: {station.standard_name})")
                inserted_count += 1

            StationRepository.upsert(session, station)

        session.commit()
        session.close()

        logging.info(f"Stations sync completed: {inserted_count} new stations inserted, {updated_count} existing stations updated")
        return inserted_count + updated_count

    except Exception as e:
        logging.error(f"Error fetching stations: {str(e)}")
        return 0

# --- Liveboard Fetching Logic ---
# List of the biggest train stations in Belgium
MAJOR_STATIONS = [
    "Brussels-Central",
    "Brussels-South",
    "Brussels-North",
    "Antwerp-Central",
    "Ghent-Sint-Pieters",
    "Liège-Guillemins",
    "Charleroi-South",
    "Bruges",
    "Leuven",
    "Namur",
    "Mechelen",
    "Mons",
    "Aalst",
    "Kortrijk",
    "Ostend",
]

def fetch_and_store_all_liveboards(delay_seconds: float = 1.5):
    """
    Fetch liveboard data for the biggest train stations in Belgium

    Args:
        delay_seconds: Delay between requests in seconds (default: 1.5s)

    Only processes major Belgian train stations defined in MAJOR_STATIONS

    Transaction handling:
    - Opens a single session/transaction for all stations
    - Uses flush() to write to DB incrementally but doesn't commit until the end
    - If ANY error occurs, ALL changes are rolled back (none of the stations are saved)
    - Only commits at the very end if everything succeeds
    """
    session = None
    try:
        logging.info("=" * 60)
        logging.info("Starting fetch_and_store_all_liveboards")
        logging.info(f"Major stations to process: {MAJOR_STATIONS}")
        logging.info("=" * 60)

        session = get_session()  # Starts a new transaction
        logging.info("Database session created successfully")

        # Get only the major stations from database
        logging.info(f"Looking up {len(MAJOR_STATIONS)} major stations in database...")

        all_stations = [StationRepository.get_by_standard_name(session, name) or StationRepository.get_by_name(session, name)
                       for name in MAJOR_STATIONS]
        all_stations = [s for s in all_stations if s is not None]

        if not all_stations:
            logging.warning("No major stations found in database")
            logging.warning("TIP: Run /api/fetch_stations first to populate the Stations table")
            session.close()
            return 0

        total_stations = len(all_stations)
        logging.info(f"Found {total_stations} major train stations in database")
        logging.info(f"Station names: {[s.name for s in all_stations]}")

        total_inserted = 0
        total_updated = 0

        for idx, station in enumerate(all_stations, 1):
            # Use standard_name for API call, fallback to name
            api_station_name = station.standard_name or station.name

            logging.info(f"[{idx}/{total_stations}] Processing station: {station.name} (API name: {api_station_name})")

            try:
                # Fetch liveboard for this station
                logging.info(f"  → Calling iRail API for {api_station_name}...")
                departures_data = irail_client.fetch_liveboard(api_station_name)

                if departures_data:
                    logging.info(f"  → Received {len(departures_data)} departures from API")
                    departures = [Departure.from_api(dep, station.id) for dep in departures_data]
                    logging.info(f"  → Converted to {len(departures)} Departure objects")

                    # Use upsert to insert new or update existing departures
                    result = DepartureRepository.upsert_batch(session, departures)
                    total_inserted += result["inserted"]
                    total_updated += result["updated"]
                    logging.info(f"  ✓ Processed {api_station_name}: {result['inserted']} new, {result['updated']} updated")
                else:
                    logging.warning(f"  ✗ No departures returned for {api_station_name}")

                # Respect API rate limits with delay
                logging.info(f"  → Waiting {delay_seconds}s before next request...")
                time.sleep(delay_seconds)

            except Exception as e:
                logging.error(f"  ✗ Error fetching liveboard for {station.name}: {str(e)}")
                import traceback
                logging.error(f"  Traceback: {traceback.format_exc()}")
                continue

        # COMMIT: Save all changes permanently to the database
        # All inserts/updates across all stations are saved as one atomic transaction
        session.commit()
        logging.info("Database changes committed successfully")

        logging.info("=" * 60)
        logging.info(f"✓ Processing complete!")
        logging.info(f"  Total stations processed: {total_stations}")
        logging.info(f"  New departures inserted: {total_inserted}")
        logging.info(f"  Existing departures updated: {total_updated}")
        logging.info(f"  Total records affected: {total_inserted + total_updated}")
        logging.info("=" * 60)
        return total_inserted + total_updated

    except Exception as e:
        # ROLLBACK: If any error occurs, undo ALL changes made in this transaction
        # None of the departures from ANY station will be saved
        if session:
            session.rollback()
            logging.warning("Transaction rolled back due to error - no data was saved")

        logging.error("=" * 60)
        logging.error(f"✗ FATAL ERROR in fetch_and_store_all_liveboards: {str(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        logging.error("=" * 60)
        return 0

    finally:
        # CLEANUP: Always close the session to release the database connection
        if session:
            session.close()
            logging.debug("Database session closed")

# --- Triggers ---
 

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


@app.schedule(schedule="0 0 * * * *", arg_name="mytimer")
def fetch_stations_scheduled(mytimer: func.TimerRequest) -> None:
    """Scheduled trigger to ingest all stations (runs daily at top of hour)"""
    logging.info(f"Timer trigger (fetch_stations) fired. Past due: {mytimer.past_due}")
    fetch_and_store_all_stations()