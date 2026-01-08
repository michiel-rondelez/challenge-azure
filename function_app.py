"""
Simplified Azure Function for Belgian Train Data
"""

import azure.functions as func
import logging
import requests
import pyodbc
from datetime import datetime
import os
import time

app = func.FunctionApp()

# Configuration
SQL_CONNECTION_STRING = os.environ.get("SQL_CONNECTION_STRING")
IRAIL_API = "https://api.irail.be/liveboard/"
USER_AGENT = "AzureTrainData/1.0 (becode.org; michiel.rondelez.pro@gmail.com)"

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
    """Fetch train data and store in database."""
    
    # Fetch from API
    try:
        response = requests.get(
            IRAIL_API,
            params={"station": station, "format": "json", "fast": "true"},
            headers={"User-Agent": USER_AGENT},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logging.error(f"API fetch failed: {e}")
        return 0
    
    # Get departures
    departures = data.get("departures", {}).get("departure", [])
    if not departures:
        return 0
    
    # Store in database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    station_name = data.get("stationinfo", {}).get("standardname", station)
    station_id = get_or_create_station(cursor, station_name)
    
    inserted = 0
    for dep in departures:
        try:
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
                int(dep.get("delay", 0)),
                1 if dep.get("canceled", 0) == 1 else 0,
                dep.get("station", "Unknown"),
                datetime.now(),
                1 if dep.get("platforminfo", {}).get("normal", "1") == "1" else 0,
                1 if dep.get("left", 0) == 1 else 0,
                dep.get("occupancy", {}).get("name", "unknown")
            )
            inserted += 1
        except Exception as e:
            logging.error(f"Insert failed: {e}")
    
    conn.commit()
    conn.close()
    
    logging.info(f"Inserted {inserted} records for {station}")
    return inserted

# HTTP Trigger
@app.route(route="fetch_trains", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def fetch_trains_http(req: func.HttpRequest) -> func.HttpResponse:
    """Fetch trains for a station via HTTP."""
    station = req.params.get('station', 'Brussels-Central')
    
    inserted = fetch_and_store_trains(station)
    
    return func.HttpResponse(
        f'{{"status": "success", "station": "{station}", "records": {inserted}}}',
        mimetype="application/json"
    )

# Timer Trigger - runs every hour
@app.schedule(schedule="0 0 * * * *", arg_name="mytimer", run_on_startup=False)
def fetch_trains_scheduled(mytimer: func.TimerRequest) -> None:
    """Fetch trains for major stations every hour."""
    stations = [
        "Brussels-Central",
        "Antwerp-Central", 
        "Ghent-Sint-Pieters",
        "Brussels-South"
    ]
    
    for i, station in enumerate(stations):
        fetch_and_store_trains(station)
        if i < len(stations) - 1:
            time.sleep(0.35)  # Rate limiting
    
    logging.info("Scheduled fetch completed")