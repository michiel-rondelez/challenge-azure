"""
SQLAlchemy-based database operations

Architecture Overview:
====================

┌──────────────────────────────────────────────────────────────┐
│                     Your Application                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Global _engine (singleton, created once)              │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Connection Pool (5 connections by default)      │ │ │
│  │  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │ │ │
│  │  │  │conn1│ │conn2│ │conn3│ │conn4│ │conn5│        │ │ │
│  │  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘        │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│           ▲                    │                            │
│           │                    ▼                            │
│   get_engine()          session borrows                     │
│   (returns existing)    connection from pool                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Request 1:  session1 = get_session()                  │ │
│  │              ↓ borrows conn1                            │ │
│  │              session1.commit()                          │ │
│  │              session1.close() → returns conn1 to pool   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Request 2:  session2 = get_session()                  │ │
│  │              ↓ reuses conn1 (100x faster!)              │ │
│  │              session2.commit()                          │ │
│  │              session2.close() → returns conn1 to pool   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────────┐
                    │  Azure SQL Server  │
                    │   (5 connections)  │
                    └────────────────────┘

Key Points:
- Engine is created ONCE (singleton pattern via _engine global)
- Connection pool is managed by the engine
- Sessions borrow connections from pool (very fast)
- Closing session returns connection to pool (doesn't close it)
- Same physical connection is reused across multiple requests
"""
import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import URL
from .db_models import Base, StationModel, DepartureModel
from .models import Station, Departure

# Global engine instance (created once and reused via singleton pattern)
# This is CRITICAL for performance - creating engines is expensive (~100ms)
# The engine manages a connection pool internally (default: 5 connections)
# Thread-safe: Can be safely shared across multiple threads/requests
_engine = None


def get_sqlalchemy_connection_string() -> str:
    """
    Convert pyodbc connection string to SQLAlchemy format

    Connection string format:
    - Input: ODBC format with DRIVER, SERVER, DATABASE, UID, PWD, etc.
    - Output: SQLAlchemy format: mssql+pyodbc:///?odbc_connect={connection_string}

    The mssql+pyodbc:// prefix tells SQLAlchemy:
    - mssql = Microsoft SQL Server database
    - pyodbc = Use pyodbc driver (not pymssql or other drivers)
    """
    conn_string = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_string:
        raise ValueError("SQL_CONNECTION_STRING environment variable not set")

    # SQLAlchemy uses mssql+pyodbc:// prefix
    # Pass the full ODBC connection string via odbc_connect parameter
    return f"mssql+pyodbc:///?odbc_connect={conn_string}"


def get_engine():
    """
    Get or create SQLAlchemy engine (singleton pattern)

    What is an Engine?
    - The Engine is the starting point for any SQLAlchemy application
    - It manages a CONNECTION POOL to the database (reuses connections efficiently)
    - One engine per database - typically created once and reused
    - Thread-safe - can be shared across multiple threads

    Connection Pool:
    - By default, SQLAlchemy maintains a pool of 5 database connections
    - When you create a session, it borrows a connection from the pool
    - When you close the session, the connection is returned to the pool (not closed)
    - This is MUCH faster than creating new connections every time

    Performance:
    - Creating an engine is relatively expensive (establishes connection pool)
    - Using an existing engine is very fast (just borrows from pool)
    - That's why we create the engine ONCE and reuse it (singleton pattern)

    Singleton Pattern:
    - First call: Creates engine and stores it in global _engine variable
    - Subsequent calls: Returns the existing _engine (very fast)
    - This means connection pool is created once and shared across all requests

    Note: echo=False means don't log SQL statements (set to True for debugging)
    """
    global _engine

    # Only create engine if it doesn't exist yet (singleton pattern)
    if _engine is None:
        connection_string = get_sqlalchemy_connection_string()
        # create_engine() establishes the connection pool but doesn't connect yet
        # Actual connections are made lazily when first needed (when creating sessions)
        _engine = create_engine(connection_string, echo=False)
        logging.debug("Created new SQLAlchemy engine with connection pool")

    return _engine


def get_session() -> Session:
    """
    Create and return a new database session.

    How it works with the Engine:
    1. get_engine() - Gets/creates the engine with connection pool
    2. sessionmaker(bind=engine) - Creates a session factory bound to the engine
    3. Session() - Creates a new session that borrows a connection from the pool
    4. When session.close() is called, connection returns to pool (not closed)

    Connection Pool Lifecycle:
    ┌─────────┐
    │  Engine │ ← Created once, maintains pool of 5 connections
    └────┬────┘
         │
    ┌────▼─────────────────────────────┐
    │  Connection Pool                 │
    │  [conn1] [conn2] [conn3] ...     │
    └────┬─────────────────────────────┘
         │
    ┌────▼────┐
    │ Session │ ← Borrows connection from pool
    └────┬────┘
         │
    session.close() → Connection returns to pool (reused later)

    IMPORTANT: Session management and transactions:
    - A new session starts an implicit transaction automatically
    - Changes are NOT saved to the database until session.commit() is called
    - If an error occurs and you don't call commit(), changes are rolled back
    - Always call session.close() when done to release the connection back to pool

    Usage pattern:
        session = get_session()  # Borrows connection from pool
        try:
            # Make changes (insert, update, delete)
            session.commit()  # Permanently save all changes
        except Exception as e:
            session.rollback()  # Undo all changes since last commit
            raise
        finally:
            session.close()  # Returns connection to pool

    Note: flush() writes to DB but doesn't commit - changes can still be rolled back
    """
    engine = get_engine()  # Get the engine (with connection pool)
    Session = sessionmaker(bind=engine)  # Create session factory
    return Session()  # Create new session (borrows from pool)


class StationRepositorySQLAlchemy:
    """Repository for Station database operations using SQLAlchemy"""

    @staticmethod
    def upsert(session: Session, station: Station) -> int:
        """
        Insert or update station, returns station ID

        Transaction handling:
        - This method does NOT commit - the caller must call session.commit()
        - Uses flush() to generate IDs but changes can still be rolled back
        - If the caller doesn't commit, all changes are automatically rolled back
        """
        # Check if station exists
        existing = session.query(StationModel).filter_by(name=station.name).first()

        if existing:
            # Update existing station
            existing.standard_name = station.standard_name
            existing.location_x = station.location_x
            existing.location_y = station.location_y
            existing.irail_id = station.irail_id
            # flush() sends pending changes to DB without committing the transaction
            # This generates the ID if needed and makes the record visible within this session
            session.flush()
            return existing.id
        else:
            # Insert new station
            new_station = StationModel(
                name=station.name,
                standard_name=station.standard_name,
                location_x=station.location_x,
                location_y=station.location_y,
                irail_id=station.irail_id,
                created_at=datetime.now()
            )
            session.add(new_station)
            # flush() executes the INSERT and generates the auto-increment ID
            # but doesn't commit - allows us to return the ID and rollback if needed
            session.flush()
            return new_station.id

    @staticmethod
    def get_or_create_simple(session: Session, station_name: str, standard_name: Optional[str] = None) -> int:
        """Get station ID by name, create if doesn't exist"""
        existing = session.query(StationModel).filter_by(name=station_name).first()
        if existing:
            return existing.id

        new_station = StationModel(
            name=station_name,
            standard_name=standard_name or station_name,
            created_at=datetime.now()
        )
        session.add(new_station)
        # flush() writes to DB and generates the ID without committing
        session.flush()
        return new_station.id

    @staticmethod
    def get_all(session: Session) -> List[Station]:
        """Get all stations from database"""
        stations = session.query(StationModel).all()
        return [
            Station(
                id=s.id,
                name=s.name,
                standard_name=s.standard_name,
                location_x=s.location_x,
                location_y=s.location_y,
                irail_id=s.irail_id
            )
            for s in stations
        ]

    @staticmethod
    def get_by_id(session: Session, station_id: int) -> Optional[Station]:
        """Get station by ID"""
        station = session.query(StationModel).filter_by(id=station_id).first()
        if not station:
            return None

        return Station(
            id=station.id,
            name=station.name,
            standard_name=station.standard_name,
            location_x=station.location_x,
            location_y=station.location_y,
            irail_id=station.irail_id
        )

    @staticmethod
    def get_by_name(session: Session, name: str) -> Optional[Station]:
        """Get station by name"""
        station = session.query(StationModel).filter_by(name=name).first()
        if not station:
            return None

        return Station(
            id=station.id,
            name=station.name,
            standard_name=station.standard_name,
            location_x=station.location_x,
            location_y=station.location_y,
            irail_id=station.irail_id
        )

    @staticmethod
    def get_by_standard_name(session: Session, standard_name: str) -> Optional[Station]:
        """Get station by standard name"""
        station = session.query(StationModel).filter_by(standard_name=standard_name).first()
        if not station:
            return None

        return Station(
            id=station.id,
            name=station.name,
            standard_name=station.standard_name,
            location_x=station.location_x,
            location_y=station.location_y,
            irail_id=station.irail_id
        )


class DepartureRepositorySQLAlchemy:
    """Repository for Departure database operations using SQLAlchemy"""

    @staticmethod
    def insert(session: Session, departure: Departure) -> None:
        """Insert a departure record"""
        new_departure = DepartureModel(
            station_id=departure.station_id,
            train_id=departure.train_id,
            vehicle=departure.vehicle,
            platform=departure.platform,
            scheduled_time=departure.scheduled_time,
            delay=departure.delay,
            direction=departure.direction,
            fetched_at=departure.fetched_at
        )
        session.add(new_departure)

    @staticmethod
    def upsert(session: Session, departure: Departure) -> None:
        """Insert or update departure based on unique combination"""
        existing = session.query(DepartureModel).filter(
            and_(
                DepartureModel.station_id == departure.station_id,
                DepartureModel.train_id == departure.train_id,
                DepartureModel.scheduled_time == departure.scheduled_time
            )
        ).first()

        if existing:
            # Update existing departure
            existing.vehicle = departure.vehicle
            existing.platform = departure.platform
            existing.delay = departure.delay
            existing.direction = departure.direction
            existing.fetched_at = departure.fetched_at
        else:
            # Insert new departure
            DepartureRepositorySQLAlchemy.insert(session, departure)

    @staticmethod
    def upsert_batch(session: Session, departures: List[Departure]) -> Dict[str, int]:
        """Upsert multiple departure records, returns counts"""
        inserted = 0
        updated = 0

        for departure in departures:
            existing = session.query(DepartureModel).filter(
                and_(
                    DepartureModel.station_id == departure.station_id,
                    DepartureModel.train_id == departure.train_id,
                    DepartureModel.scheduled_time == departure.scheduled_time
                )
            ).first()

            if existing:
                # Update
                existing.vehicle = departure.vehicle
                existing.platform = departure.platform
                existing.delay = departure.delay
                existing.direction = departure.direction
                existing.fetched_at = departure.fetched_at
                updated += 1
            else:
                # Insert
                DepartureRepositorySQLAlchemy.insert(session, departure)
                inserted += 1

        return {"inserted": inserted, "updated": updated}

    @staticmethod
    def get_recent(session: Session, minutes: int = 60, limit: int = 100) -> List[Departure]:
        """Get recent departures within specified minutes"""
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        departures = session.query(DepartureModel).filter(
            DepartureModel.fetched_at > cutoff_time
        ).order_by(DepartureModel.fetched_at.desc()).limit(limit).all()

        return [
            Departure(
                id=d.id,
                station_id=d.station_id,
                train_id=d.train_id,
                vehicle=d.vehicle,
                platform=d.platform,
                scheduled_time=d.scheduled_time,
                delay=d.delay,
                direction=d.direction,
                fetched_at=d.fetched_at
            )
            for d in departures
        ]

    @staticmethod
    def get_by_station(session: Session, station_id: int, limit: int = 50) -> List[Departure]:
        """Get departures for a specific station"""
        departures = session.query(DepartureModel).filter(
            DepartureModel.station_id == station_id
        ).order_by(DepartureModel.scheduled_time.desc()).limit(limit).all()

        return [
            Departure(
                id=d.id,
                station_id=d.station_id,
                train_id=d.train_id,
                vehicle=d.vehicle,
                platform=d.platform,
                scheduled_time=d.scheduled_time,
                delay=d.delay,
                direction=d.direction,
                fetched_at=d.fetched_at
            )
            for d in departures
        ]
