"""SQLAlchemy ORM models for database tables"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class StationModel(Base):
    """SQLAlchemy model for Stations table"""
    __tablename__ = 'Stations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    standard_name = Column(String(255))
    location_x = Column(Float)
    location_y = Column(Float)
    irail_id = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)

    # Relationship
    departures = relationship("DepartureModel", back_populates="station")

    def __repr__(self):
        return f"<Station(id={self.id}, name='{self.name}')>"


class DepartureModel(Base):
    """SQLAlchemy model for Departures table"""
    __tablename__ = 'Departures'

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey('Stations.id'), nullable=False)
    train_id = Column(String(50), nullable=False)
    vehicle = Column(String(50))
    platform = Column(String(10))
    scheduled_time = Column(DateTime, nullable=False)
    delay = Column(Integer, default=0)
    canceled = Column(Boolean, default=False)
    has_left = Column(Boolean, default=False)
    is_normal_platform = Column(Boolean, default=True)
    direction = Column(String(255))
    occupancy = Column(String(50))
    fetched_at = Column(DateTime, default=datetime.now)

    # Relationship
    station = relationship("StationModel", back_populates="departures")

    def __repr__(self):
        return f"<Departure(id={self.id}, train_id='{self.train_id}', station_id={self.station_id})>"
