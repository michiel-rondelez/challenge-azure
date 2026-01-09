"""Database utilities and operations"""
import os
import pyodbc
import logging
from typing import Optional, List
from datetime import datetime
from .models import Station, Departure


def get_connection_string() -> str:
    """Get SQL connection string from environment"""
    conn_string = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_string:
        raise ValueError("SQL_CONNECTION_STRING environment variable not set")
    return conn_string


def get_db_connection():
    """Create and return a database connection"""
    return pyodbc.connect(get_connection_string())


class StationRepository:
    """Repository for Station database operations"""

    @staticmethod
    def upsert(cursor, station: Station) -> int:
        """Insert or update station, returns station ID"""
        # Check if station exists
        cursor.execute("SELECT id FROM Stations WHERE name = ?", (station.name,))
        row = cursor.fetchone()

        if row:
            # Update existing station
            cursor.execute("""
                UPDATE Stations
                SET standard_name = ?, location_x = ?, location_y = ?, irail_id = ?
                WHERE name = ?
            """, (station.standard_name, station.location_x, station.location_y,
                  station.irail_id, station.name))
            return row[0]
        else:
            # Insert new station
            cursor.execute("""
                INSERT INTO Stations (name, standard_name, location_x, location_y, irail_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (station.name, station.standard_name, station.location_x,
                  station.location_y, station.irail_id, datetime.now()))
            cursor.execute("SELECT @@IDENTITY")
            return cursor.fetchone()[0]

    @staticmethod
    def get_or_create_simple(cursor, station_name: str, standard_name: Optional[str] = None) -> int:
        """Get station ID by name, create if doesn't exist (simple version)"""
        cursor.execute("SELECT id FROM Stations WHERE name = ?", (station_name,))
        row = cursor.fetchone()
        if row:
            return row[0]

        cursor.execute(
            "INSERT INTO Stations (name, standard_name, created_at) VALUES (?, ?, ?)",
            (station_name, standard_name or station_name, datetime.now())
        )
        cursor.execute("SELECT @@IDENTITY")
        return cursor.fetchone()[0]

    @staticmethod
    def get_all(cursor) -> List[Station]:
        """Get all stations from database"""
        cursor.execute("SELECT id, name, standard_name FROM Stations")
        return [Station(id=row[0], name=row[1], standard_name=row[2])
                for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(cursor, station_id: int) -> Optional[Station]:
        """Get station by ID"""
        cursor.execute("""
            SELECT id, name, standard_name, location_x, location_y, irail_id, created_at
            FROM Stations WHERE id = ?
        """, (station_id,))
        row = cursor.fetchone()
        return Station.from_db_row(row) if row else None


class DepartureRepository:
    """Repository for Departure database operations"""

    @staticmethod
    def insert(cursor, departure: Departure) -> None:
        """Insert a departure record"""
        cursor.execute("""
            INSERT INTO Departures (station_id, train_id, vehicle, platform, scheduled_time, delay, direction, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (departure.station_id, departure.train_id, departure.vehicle,
              departure.platform, departure.scheduled_time, departure.delay,
              departure.direction, departure.fetched_at))

    @staticmethod
    def insert_batch(cursor, departures: List[Departure]) -> int:
        """Insert multiple departure records, returns count inserted"""
        count = 0
        for departure in departures:
            DepartureRepository.insert(cursor, departure)
            count += 1
        return count

    @staticmethod
    def get_recent(cursor, minutes: int = 60, limit: int = 100) -> List[Departure]:
        """Get recent departures within specified minutes"""
        cursor.execute(f"""
            SELECT TOP {limit} id, station_id, train_id, vehicle, platform,
                   scheduled_time, delay, direction, fetched_at
            FROM Departures
            WHERE fetched_at > DATEADD(minute, -{minutes}, GETDATE())
            ORDER BY fetched_at DESC
        """)
        return [Departure.from_db_row(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_station(cursor, station_id: int, limit: int = 50) -> List[Departure]:
        """Get departures for a specific station"""
        cursor.execute(f"""
            SELECT TOP {limit} id, station_id, train_id, vehicle, platform,
                   scheduled_time, delay, direction, fetched_at
            FROM Departures
            WHERE station_id = ?
            ORDER BY scheduled_time DESC
        """, (station_id,))
        return [Departure.from_db_row(row) for row in cursor.fetchall()]


def execute_with_connection(func):
    """Decorator to handle connection management"""
    def wrapper(*args, **kwargs):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            result = func(cursor, *args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"Database error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    return wrapper
