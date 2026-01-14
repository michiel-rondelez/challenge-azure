"""
Database verification script to check if data is being stored correctly.
Run this script to verify stations and departures are in the database.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from shared.db_sqlalchemy import get_session, StationRepositorySQLAlchemy, DepartureRepositorySQLAlchemy
from shared.db_models import StationModel, DepartureModel


def load_local_settings():
    """Load environment variables from local.settings.json"""
    settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, 'r') as f:
            settings = json.load(f)
            for key, value in settings.get("Values", {}).items():
                os.environ[key] = value
        print("✓ Loaded environment variables from local.settings.json")
    else:
        print("⚠ WARNING: local.settings.json not found")


def verify_database():
    """Verify database contents and schema"""
    print("=" * 70)
    print("DATABASE VERIFICATION")
    print("=" * 70)

    try:
        session = get_session()
        print("✓ Database connection successful")

        # Check Stations
        print("\n" + "=" * 70)
        print("STATIONS TABLE")
        print("=" * 70)

        stations_count = session.query(StationModel).count()
        print(f"Total stations in database: {stations_count}")

        if stations_count > 0:
            # Show first 5 stations
            stations = session.query(StationModel).limit(5).all()
            print("\nFirst 5 stations:")
            for station in stations:
                print(f"  - ID: {station.id:3d} | Name: {station.name:30s} | Standard: {station.standard_name or 'N/A'}")

            # Check for major stations
            print("\nChecking for major stations:")
            major_stations = [
                "Brussels-Central", "Brussels-South", "Brussels-North",
                "Antwerp-Central", "Ghent-Sint-Pieters"
            ]
            for name in major_stations:
                station = session.query(StationModel).filter(
                    (StationModel.name == name) | (StationModel.standard_name == name)
                ).first()
                status = "✓ FOUND" if station else "✗ MISSING"
                print(f"  {status}: {name}")
        else:
            print("\n⚠ WARNING: No stations found in database!")
            print("  → Run: curl http://localhost:7071/api/fetch_stations")

        # Check Departures
        print("\n" + "=" * 70)
        print("DEPARTURES TABLE")
        print("=" * 70)

        departures_count = session.query(DepartureModel).count()
        print(f"Total departures in database: {departures_count}")

        if departures_count > 0:
            # Show recent departures (last 10)
            recent = session.query(DepartureModel).order_by(
                DepartureModel.fetched_at.desc()
            ).limit(10).all()

            print("\nMost recent 10 departures:")
            print(f"{'ID':<6} {'Station ID':<10} {'Train':<12} {'Platform':<8} {'Delay':<6} {'Fetched At':<20}")
            print("-" * 70)
            for dep in recent:
                fetched = dep.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if dep.fetched_at else "N/A"
                print(f"{dep.id:<6} {dep.station_id:<10} {dep.train_id:<12} {dep.platform or 'N/A':<8} {dep.delay:<6} {fetched:<20}")

            # Count by station
            print("\nDepartures per station (top 10):")
            from sqlalchemy import func
            station_counts = session.query(
                StationModel.name,
                func.count(DepartureModel.id).label('count')
            ).join(DepartureModel).group_by(StationModel.name).order_by(
                func.count(DepartureModel.id).desc()
            ).limit(10).all()

            for station_name, count in station_counts:
                print(f"  {station_name:40s}: {count:5d} departures")

            # Check data freshness
            print("\nData freshness:")
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent_count = session.query(DepartureModel).filter(
                DepartureModel.fetched_at > one_hour_ago
            ).count()
            print(f"  Departures fetched in last hour: {recent_count}")

            if recent_count == 0:
                print("  ⚠ WARNING: No recent data (older than 1 hour)")
                print("  → Run: curl http://localhost:7071/api/fetch_all_liveboards")
            else:
                print("  ✓ Data is fresh")

        else:
            print("\n⚠ WARNING: No departures found in database!")
            print("  → Run: curl http://localhost:7071/api/fetch_all_liveboards")

        # Check for data quality issues
        print("\n" + "=" * 70)
        print("DATA QUALITY CHECKS")
        print("=" * 70)

        # Check for null values
        null_station_ids = session.query(DepartureModel).filter(
            DepartureModel.station_id == None
        ).count()
        print(f"Departures with null station_id: {null_station_ids}")
        if null_station_ids > 0:
            print("  ✗ ERROR: Found departures without station_id")
        else:
            print("  ✓ All departures have station_id")

        # Check for null scheduled times
        null_times = session.query(DepartureModel).filter(
            DepartureModel.scheduled_time == None
        ).count()
        print(f"Departures with null scheduled_time: {null_times}")
        if null_times > 0:
            print("  ⚠ WARNING: Found departures without scheduled_time")
        else:
            print("  ✓ All departures have scheduled_time")

        session.close()

        print("\n" + "=" * 70)
        print("VERIFICATION COMPLETE")
        print("=" * 70)

        # Summary
        if stations_count == 0:
            print("\n⚠ ACTION REQUIRED: Populate stations first")
            print("  curl http://localhost:7071/api/fetch_stations")
        elif departures_count == 0:
            print("\n⚠ ACTION REQUIRED: Fetch departure data")
            print("  curl http://localhost:7071/api/fetch_all_liveboards")
        else:
            print("\n✓ Database contains both stations and departures!")

    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    load_local_settings()
    verify_database()
