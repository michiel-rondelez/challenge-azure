"""
Simplified Azure Function for Belgian Train Data
With Application Insights Custom Telemetry
"""

import azure.functions as func
import logging
import requests
import pyodbc
from datetime import datetime
import os
import time

# Application Insights imports (optional - for custom metrics)
try:
    from opencensus.ext.azure.log_exporter import AzureLogHandler
    from opencensus.ext.azure import metrics_exporter
    from opencensus.stats import aggregation as aggregation_module
    from opencensus.stats import measure as measure_module
    from opencensus.stats import stats as stats_module
    from opencensus.stats import view as view_module
    from opencensus.tags import tag_map as tag_map_module
    APPINSIGHTS_AVAILABLE = True
except ImportError:
    APPINSIGHTS_AVAILABLE = False
    logging.warning("Application Insights SDK not available - custom metrics disabled")

app = func.FunctionApp()

# Configuration
SQL_CONNECTION_STRING = os.environ.get("SQL_CONNECTION_STRING")
APPINSIGHTS_CONNECTION_STRING = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
IRAIL_API = "https://api.irail.be/liveboard/"
USER_AGENT = "AzureTrainData/1.0 (becode.org; michiel.rondelez.pro@gmail.com)"

# Initialize Application Insights custom metrics (if available)
if APPINSIGHTS_AVAILABLE and APPINSIGHTS_CONNECTION_STRING:
    # Create a metrics exporter
    exporter = metrics_exporter.new_metrics_exporter(
        connection_string=APPINSIGHTS_CONNECTION_STRING
    )

    # Create measures for custom metrics
    trains_fetched_measure = measure_module.MeasureInt(
        "trains_fetched", "Number of trains fetched", "trains"
    )
    api_response_time_measure = measure_module.MeasureFloat(
        "api_response_time", "API response time", "ms"
    )
    delay_seconds_measure = measure_module.MeasureInt(
        "train_delay_seconds", "Train delay in seconds", "seconds"
    )

    # Create views for aggregation
    stats = stats_module.stats
    view_manager = stats.view_manager
    view_manager.register_exporter(exporter)

    trains_fetched_view = view_module.View(
        "trains_fetched_view",
        "Number of trains fetched per station",
        ["station"],
        trains_fetched_measure,
        aggregation_module.SumAggregation()
    )

    api_response_view = view_module.View(
        "api_response_time_view",
        "API response time by station",
        ["station"],
        api_response_time_measure,
        aggregation_module.LastValueAggregation()
    )

    delay_view = view_module.View(
        "train_delays_view",
        "Train delays by station",
        ["station"],
        delay_seconds_measure,
        aggregation_module.DistributionAggregation([0, 60, 300, 600, 1800])  # 0s, 1m, 5m, 10m, 30m
    )

    view_manager.register_view(trains_fetched_view)
    view_manager.register_view(api_response_view)
    view_manager.register_view(delay_view)

    mmap = stats.stats_recorder
else:
    mmap = None
    logging.info("Custom Application Insights metrics not configured")

def get_db_connection():
    """Get database connection."""
    return pyodbc.connect(SQL_CONNECTION_STRING)

def get_or_create_station(cursor, station_name):
    """Get station ID or create if new."""
    cursor.execute("SELECT id FROM Stations WHERE name = ?", station_name)
    row = cursor.fetchone()
    
    if row:
        return row[0]
    
    cursor.execute(
        "INSERT INTO Stations (name, standard_name, created_at) VALUES (?, ?, ?)",
        station_name, station_name, datetime.now()
    )
    cursor.execute("SELECT @@IDENTITY")
    return cursor.fetchone()[0]

def fetch_and_store_trains(station="Brussels-Central"):
    """Fetch train data and store in database with custom telemetry."""

    # Track API response time
    api_start_time = time.time()

    # Fetch from API
    try:
        logging.info(f"Fetching train data for station: {station}")
        response = requests.get(
            IRAIL_API,
            params={"station": station, "format": "json", "fast": "true"},
            headers={"User-Agent": USER_AGENT},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Log API response time
        api_duration_ms = (time.time() - api_start_time) * 1000
        logging.info(f"API response time: {api_duration_ms:.2f}ms for {station}")

        # Track custom metric: API response time
        if mmap:
            tmap = tag_map_module.TagMap()
            tmap.insert("station", station)
            mmap.measure_float_put(api_response_time_measure, api_duration_ms)
            mmap.record(tmap)

    except requests.exceptions.Timeout:
        logging.error(f"API timeout for station {station}")
        return 0
    except requests.exceptions.RequestException as e:
        logging.error(f"API fetch failed for {station}: {e}")
        return 0
    except Exception as e:
        logging.error(f"Unexpected error fetching data for {station}: {e}")
        return 0

    # Get departures
    departures = data.get("departures", {}).get("departure", [])
    if not departures:
        logging.warning(f"No departures found for {station}")
        return 0

    logging.info(f"Found {len(departures)} departures for {station}")

    # Store in database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return 0

    station_name = data.get("stationinfo", {}).get("standardname", station)
    station_id = get_or_create_station(cursor, station_name)

    inserted = 0
    total_delay = 0
    cancelled_count = 0

    for dep in departures:
        try:
            delay_seconds = int(dep.get("delay", 0))
            is_cancelled = 1 if dep.get("canceled", 0) == 1 else 0

            cursor.execute("""
                INSERT INTO Departures
                (station_id, train_id, vehicle, platform, scheduled_time,
                 delay, canceled, direction, fetched_at,
                 is_normal_platform, has_left, occupancy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                station_id,
                dep.get("id", ""),
                dep.get("vehicle", ""),
                dep.get("platform", "?"),
                datetime.fromtimestamp(int(dep.get("time", 0))),
                delay_seconds,
                is_cancelled,
                dep.get("station", "Unknown"),
                datetime.now(),
                1 if dep.get("platforminfo", {}).get("normal", "1") == "1" else 0,
                1 if dep.get("left", 0) == 1 else 0,
                dep.get("occupancy", {}).get("name", "unknown")
            )
            inserted += 1
            total_delay += delay_seconds
            cancelled_count += is_cancelled

            # Track custom metric: train delays
            if mmap and delay_seconds > 0:
                tmap = tag_map_module.TagMap()
                tmap.insert("station", station)
                mmap.measure_int_put(delay_seconds_measure, delay_seconds)
                mmap.record(tmap)

        except Exception as e:
            logging.error(f"Insert failed for train {dep.get('id', 'unknown')}: {e}")

    conn.commit()
    conn.close()

    # Calculate statistics
    avg_delay = total_delay / inserted if inserted > 0 else 0

    # Log detailed statistics
    logging.info(f"Successfully inserted {inserted} records for {station}")
    logging.info(f"Statistics - Avg delay: {avg_delay:.0f}s, Cancelled: {cancelled_count}, Total trains: {len(departures)}")

    # Track custom metric: trains fetched
    if mmap:
        tmap = tag_map_module.TagMap()
        tmap.insert("station", station)
        mmap.measure_int_put(trains_fetched_measure, inserted)
        mmap.record(tmap)

    return inserted

# HTTP Trigger
@app.route(route="fetch_trains", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def fetch_trains_http(req: func.HttpRequest) -> func.HttpResponse:
    """Fetch trains for a station via HTTP with detailed logging."""
    station = req.params.get('station', 'Brussels-Central')

    logging.info(f"HTTP trigger invoked for station: {station}")

    start_time = time.time()
    inserted = fetch_and_store_trains(station)
    duration_ms = (time.time() - start_time) * 1000

    logging.info(f"HTTP trigger completed in {duration_ms:.2f}ms - {inserted} records inserted")

    if inserted == 0:
        return func.HttpResponse(
            f'{{"status": "error", "station": "{station}", "message": "No records inserted - check logs"}}',
            status_code=500,
            mimetype="application/json"
        )

    return func.HttpResponse(
        f'{{"status": "success", "station": "{station}", "records_inserted": {inserted}, "duration_ms": {duration_ms:.2f}}}',
        mimetype="application/json"
    )

# Timer Trigger - runs every hour
@app.schedule(schedule="0 0 * * * *", arg_name="mytimer", run_on_startup=False)
def fetch_trains_scheduled(mytimer: func.TimerRequest) -> None:
    """Fetch trains for major stations every hour with comprehensive logging."""
    logging.info("===== SCHEDULED FETCH STARTED =====")

    stations = [
        "Brussels-Central",
        "Antwerp-Central",
        "Ghent-Sint-Pieters",
        "Brussels-South"
    ]

    total_records = 0
    start_time = time.time()

    for i, station in enumerate(stations):
        logging.info(f"Processing station {i+1}/{len(stations)}: {station}")
        records = fetch_and_store_trains(station)
        total_records += records

        if i < len(stations) - 1:
            time.sleep(0.35)  # Rate limiting between API calls

    duration_seconds = time.time() - start_time

    logging.info(f"===== SCHEDULED FETCH COMPLETED =====")
    logging.info(f"Total records inserted: {total_records} across {len(stations)} stations")
    logging.info(f"Total execution time: {duration_seconds:.2f}s")

    # Track custom metric: total batch execution time
    if mmap:
        tmap = tag_map_module.TagMap()
        tmap.insert("trigger_type", "timer")
        mmap.measure_int_put(trains_fetched_measure, total_records)
        mmap.record(tmap)