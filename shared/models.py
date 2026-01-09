"""Data models for stations and departures"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Station:
    """Station model representing a train station"""
    id: Optional[int] = None
    name: str = ""
    standard_name: str = ""
    location_x: Optional[float] = None
    location_y: Optional[float] = None
    irail_id: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict) -> 'Station':
        """Create Station from iRail API response"""
        return cls(
            name=data.get("name", ""),
            standard_name=data.get("standardname", ""),
            location_x=data.get("locationX"),
            location_y=data.get("locationY"),
            irail_id=data.get("id")
        )

    @classmethod
    def from_db_row(cls, row) -> 'Station':
        """Create Station from database row"""
        return cls(
            id=row[0],
            name=row[1],
            standard_name=row[2],
            location_x=row[3] if len(row) > 3 else None,
            location_y=row[4] if len(row) > 4 else None,
            irail_id=row[5] if len(row) > 5 else None,
            created_at=row[6] if len(row) > 6 else None
        )


@dataclass
class Departure:
    """Departure model representing a train departure"""
    id: Optional[int] = None
    station_id: int = 0
    train_id: str = ""
    vehicle: str = ""
    platform: str = ""
    scheduled_time: Optional[datetime] = None
    delay: int = 0
    direction: str = ""
    fetched_at: Optional[datetime] = None

    @classmethod
    def from_api(cls, data: dict, station_id: int) -> 'Departure':
        """Create Departure from iRail API liveboard response"""
        scheduled_time = None
        time_value = data.get("time")
        if time_value:
            try:
                scheduled_time = datetime.fromtimestamp(int(time_value))
            except (ValueError, TypeError):
                pass

        return cls(
            station_id=station_id,
            train_id=data.get("id", ""),
            vehicle=data.get("vehicle", ""),
            platform=data.get("platform", ""),
            scheduled_time=scheduled_time,
            delay=int(data.get("delay", 0)),
            direction=data.get("station", ""),
            fetched_at=datetime.now()
        )

    @classmethod
    def from_db_row(cls, row) -> 'Departure':
        """Create Departure from database row"""
        return cls(
            id=row[0],
            station_id=row[1],
            train_id=row[2],
            vehicle=row[3],
            platform=row[4],
            scheduled_time=row[5],
            delay=row[6],
            direction=row[7],
            fetched_at=row[8]
        )
