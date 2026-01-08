import azure.functions as func
import logging
import requests
import pyodbc
from datetime import datetime
import os
import time

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
SQL_CONN = os.environ.get("SQL_CONNECTION_STRING")
IRAIL_API = "https://api.irail.be/"
USER_AGENT = "AzureTrainData/1.0 (becode.org; michiel.rondelez.pro@gmail.com)"

# --- Database Helpers ---
def get_db_connection():
    return pyodbc.connect(SQL_CONN)

def get_or_create_station(cursor, station_name):
    cursor.execute("SELECT id FROM Stations WHERE name = ?", (station_name,))
    row = cursor.fetchone()
    if row: return row[0]

    cursor.execute("INSERT INTO Stations (name, standard_name, created_at) VALUES (?, ?, ?)",
                   (station_name, station_name, datetime.now()))
    cursor.execute("SELECT @@IDENTITY")
    return cursor.fetchone()[0]

# --- Main Logic ---
def fetch_and_store_trains(station="Brussels-Central"):
    try:
        res = requests.get(IRAIL_API + "liveboard/", params={"station": station, "format": "json", "fast": "true"},
                           headers={"User-Agent": USER_AGENT}, timeout=10)
        res.raise_for_status()
        data = res.json()

        departures = data.get("departures", {}).get("departure", [])
        if not departures: return 0

        conn = get_db_connection()
        cursor = conn.cursor()

        station_name = data.get("stationinfo", {}).get("standardname", station)
        station_id = get_or_create_station(cursor, station_name)

        inserted_count = 0
        for dep in departures:
            delay = int(dep.get("delay", 0))
            cursor.execute("""
                INSERT INTO Departures (station_id, train_id, vehicle, platform, scheduled_time, delay, direction, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                station_id, dep.get("id"), dep.get("vehicle"), dep.get("platform"),
                datetime.fromtimestamp(int(dep.get("time"))), delay, dep.get("station"), datetime.now()
            )
            inserted_count += 1

        conn.commit()
        conn.close()

        logging.info(f"Successfully inserted {inserted_count} records for {station}")
        return inserted_count

    except Exception as e:
        logging.error(f"Error for {station}: {str(e)}")
        return 0

# --- Triggers ---
@app.route(route="fetch_trains", auth_level=func.AuthLevel.FUNCTION)
def fetch_trains_http(req: func.HttpRequest) -> func.HttpResponse:
    station = req.params.get('station', 'Brussels-Central')
    count = fetch_and_store_trains(station)
    return func.HttpResponse(f"Inserted {count} records for {station}", status_code=200 if count > 0 else 500)

@app.schedule(schedule="0 0 * * * *", arg_name="mytimer")
def fetch_trains_scheduled(mytimer: func.TimerRequest) -> None:
    for station in ["Brussels-Central", "Antwerp-Central", "Ghent-Sint-Pieters"]:
        fetch_and_store_trains(station)
        time.sleep(1) # Respect API limits