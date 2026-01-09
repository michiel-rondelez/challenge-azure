"""
Database connection test script and health checks
Run with: python tests/test_database.py
Run health check: python tests/test_database.py --health
Run performance test: python tests/test_database.py --performance
"""
import os
import sys
import json
import pyodbc
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

# Set ODBC configuration path for macOS (required for Homebrew-installed drivers)
os.environ['ODBCSYSINI'] = '/opt/homebrew/etc'

# Add parent directory to path so we can import from function_app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_local_settings():
    """Load connection string from local.settings.json"""
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'local.settings.json'
    )

    if os.path.exists(settings_path):
        with open(settings_path, 'r') as f:
            settings = json.load(f)
            return settings.get('Values', {}).get('SQL_CONNECTION_STRING')
    return None

def test_connection():
    """Test basic database connection"""
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)

    # Get connection string from environment or local.settings.json
    conn_string = os.environ.get("SQL_CONNECTION_STRING") or load_local_settings()

    if not conn_string:
        print("❌ ERROR: SQL_CONNECTION_STRING not found")
        print("\nMake sure it's set in local.settings.json or as environment variable:")
        print('  export SQL_CONNECTION_STRING="your_connection_string"')
        return False

    print(f"\n✓ Connection string found (length: {len(conn_string)} chars)")

    try:
        # Test connection
        print("\n[1/5] Attempting to connect to database...")
        conn = pyodbc.connect(conn_string, timeout=10)
        print("✓ Connection successful!")

        # Test cursor
        print("\n[2/5] Creating cursor...")
        cursor = conn.cursor()
        print("✓ Cursor created!")

        # Test simple query
        print("\n[3/5] Running test query (SELECT @@VERSION)...")
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"✓ Database version: {version[:80]}...")

        # Check if Stations table exists
        print("\n[4/5] Checking if Stations table exists...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'Stations'
        """)
        exists = cursor.fetchone()[0]
        if exists:
            print("✓ Stations table exists!")

            # Count stations
            cursor.execute("SELECT COUNT(*) FROM Stations")
            count = cursor.fetchone()[0]
            print(f"  → Current station count: {count}")

            # Show some stations if any exist
            if count > 0:
                cursor.execute("SELECT TOP 5 id, name, created_at FROM Stations ORDER BY created_at DESC")
                print("\n  Recent stations:")
                for row in cursor.fetchall():
                    print(f"    - ID {row[0]}: {row[1]} (created: {row[2]})")
        else:
            print("⚠ Stations table does NOT exist")
            print("  Run your schema creation script first!")

        # Check if Departures table exists
        print("\n[5/5] Checking if Departures table exists...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'Departures'
        """)
        exists = cursor.fetchone()[0]
        if exists:
            print("✓ Departures table exists!")

            # Count departures
            cursor.execute("SELECT COUNT(*) FROM Departures")
            count = cursor.fetchone()[0]
            print(f"  → Current departure count: {count}")
        else:
            print("⚠ Departures table does NOT exist")
            print("  Run your schema creation script first!")

        # Clean up
        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Database connection is working!")
        print("=" * 60)
        return True

    except pyodbc.Error as e:
        print(f"\n❌ DATABASE ERROR: {str(e)}")
        print("\nCommon issues:")
        print("  1. Check your connection string is correct")
        print("  2. Verify database server is running and accessible")
        print("  3. Check firewall rules allow your IP address")
        print("  4. Verify credentials are correct")
        return False

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {str(e)}")
        return False

def test_database_health(conn_string: str) -> Dict[str, Any]:
    """
    Comprehensive database health check
    Returns health metrics and status
    """
    health = {
        "status": "healthy",
        "checks": {},
        "metrics": {},
        "timestamp": datetime.now().isoformat()
    }

    try:
        # Connection test
        start_time = time.time()
        conn = pyodbc.connect(conn_string, timeout=10)
        connection_time = (time.time() - start_time) * 1000  # ms
        health["metrics"]["connection_time_ms"] = round(connection_time, 2)
        health["checks"]["connection"] = "pass"

        cursor = conn.cursor()

        # Query performance test
        start_time = time.time()
        cursor.execute("SELECT @@VERSION")
        cursor.fetchone()
        query_time = (time.time() - start_time) * 1000
        health["metrics"]["simple_query_time_ms"] = round(query_time, 2)
        health["checks"]["query_performance"] = "pass" if query_time < 1000 else "warning"

        # Check table existence
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME IN ('Stations', 'Departures')
        """)
        existing_tables = [row[0] for row in cursor.fetchall()]
        health["checks"]["stations_table"] = "pass" if "Stations" in existing_tables else "fail"
        health["checks"]["departures_table"] = "pass" if "Departures" in existing_tables else "fail"

        # Data freshness check (for Departures)
        if "Departures" in existing_tables:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    MAX(fetched_at) as latest_fetch,
                    DATEDIFF(MINUTE, MAX(fetched_at), GETDATE()) as minutes_since_last
                FROM Departures
            """)
            row = cursor.fetchone()
            if row and row[0] > 0:
                health["metrics"]["total_departures"] = row[0]
                health["metrics"]["latest_fetch"] = row[1].isoformat() if row[1] else None
                health["metrics"]["minutes_since_last_fetch"] = row[2] if row[2] is not None else 9999

                # Alert if data is stale (no data in last 30 minutes)
                if row[2] and row[2] > 30:
                    health["checks"]["data_freshness"] = "warning"
                    health["status"] = "degraded"
                else:
                    health["checks"]["data_freshness"] = "pass"
            else:
                health["checks"]["data_freshness"] = "warning"
                health["metrics"]["total_departures"] = 0

        # Row count checks
        if "Stations" in existing_tables:
            cursor.execute("SELECT COUNT(*) FROM Stations")
            station_count = cursor.fetchone()[0]
            health["metrics"]["total_stations"] = station_count
            health["checks"]["stations_populated"] = "pass" if station_count > 0 else "warning"

        # Database size check
        cursor.execute("""
            SELECT
                SUM(size) * 8 / 1024.0 as size_mb
            FROM sys.master_files
            WHERE database_id = DB_ID()
        """)
        db_size = cursor.fetchone()[0]
        if db_size:
            health["metrics"]["database_size_mb"] = round(db_size, 2)

        # Active connections check
        cursor.execute("""
            SELECT COUNT(*)
            FROM sys.dm_exec_sessions
            WHERE is_user_process = 1
        """)
        active_connections = cursor.fetchone()[0]
        health["metrics"]["active_connections"] = active_connections

        cursor.close()
        conn.close()

        # Determine overall status
        if any(v == "fail" for v in health["checks"].values()):
            health["status"] = "unhealthy"
        elif any(v == "warning" for v in health["checks"].values()):
            health["status"] = "degraded"

    except pyodbc.Error as e:
        health["status"] = "unhealthy"
        health["error"] = str(e)
        health["checks"]["connection"] = "fail"
    except Exception as e:
        health["status"] = "error"
        health["error"] = str(e)

    return health


def test_database_performance(conn_string: str) -> Dict[str, Any]:
    """
    Performance benchmark tests
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }

    try:
        conn = pyodbc.connect(conn_string, timeout=30)
        cursor = conn.cursor()

        # Test 1: Simple SELECT performance
        iterations = 10
        times = []
        for _ in range(iterations):
            start = time.time()
            cursor.execute("SELECT @@VERSION")
            cursor.fetchone()
            times.append((time.time() - start) * 1000)

        results["tests"]["simple_select"] = {
            "avg_ms": round(sum(times) / len(times), 2),
            "min_ms": round(min(times), 2),
            "max_ms": round(max(times), 2)
        }

        # Test 2: Station lookup performance
        cursor.execute("SELECT COUNT(*) FROM Stations")
        if cursor.fetchone()[0] > 0:
            times = []
            for _ in range(iterations):
                start = time.time()
                cursor.execute("SELECT TOP 10 * FROM Stations ORDER BY created_at DESC")
                cursor.fetchall()
                times.append((time.time() - start) * 1000)

            results["tests"]["station_query"] = {
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2)
            }

        # Test 3: Complex JOIN query (if data exists)
        cursor.execute("SELECT COUNT(*) FROM Departures")
        if cursor.fetchone()[0] > 0:
            times = []
            for _ in range(iterations):
                start = time.time()
                cursor.execute("""
                    SELECT TOP 50 s.name, d.vehicle, d.delay, d.scheduled_time
                    FROM Departures d
                    INNER JOIN Stations s ON d.station_id = s.id
                    ORDER BY d.fetched_at DESC
                """)
                cursor.fetchall()
                times.append((time.time() - start) * 1000)

            results["tests"]["join_query"] = {
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2)
            }

        # Test 4: INSERT performance (with rollback)
        times = []
        for _ in range(5):
            start = time.time()
            cursor.execute("""
                INSERT INTO Stations (name, standard_name, created_at)
                VALUES (?, ?, ?)
            """, (f"TEST_STATION_{time.time()}", "TEST", datetime.now()))
            times.append((time.time() - start) * 1000)

        conn.rollback()  # Don't actually insert test data

        results["tests"]["insert_performance"] = {
            "avg_ms": round(sum(times) / len(times), 2),
            "min_ms": round(min(times), 2),
            "max_ms": round(max(times), 2)
        }

        cursor.close()
        conn.close()

    except Exception as e:
        results["error"] = str(e)

    return results


def print_health_report(health: Dict[str, Any]):
    """Pretty print health check results"""
    print("\n" + "=" * 60)
    print("DATABASE HEALTH CHECK REPORT")
    print("=" * 60)

    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌",
        "error": "💥"
    }

    print(f"\nOverall Status: {status_emoji.get(health['status'], '?')} {health['status'].upper()}")
    print(f"Timestamp: {health['timestamp']}")

    if health.get("error"):
        print(f"\n❌ Error: {health['error']}")

    if health.get("checks"):
        print("\n--- Health Checks ---")
        for check, status in health["checks"].items():
            emoji = "✅" if status == "pass" else "⚠️" if status == "warning" else "❌"
            print(f"  {emoji} {check}: {status}")

    if health.get("metrics"):
        print("\n--- Metrics ---")
        for metric, value in health["metrics"].items():
            print(f"  • {metric}: {value}")

    print("\n" + "=" * 60)


def print_performance_report(results: Dict[str, Any]):
    """Pretty print performance test results"""
    print("\n" + "=" * 60)
    print("DATABASE PERFORMANCE BENCHMARK")
    print("=" * 60)

    print(f"\nTimestamp: {results['timestamp']}")

    if results.get("error"):
        print(f"\n❌ Error: {results['error']}")
        return

    for test_name, metrics in results.get("tests", {}).items():
        print(f"\n--- {test_name.replace('_', ' ').title()} ---")
        print(f"  Average: {metrics['avg_ms']} ms")
        print(f"  Min: {metrics['min_ms']} ms")
        print(f"  Max: {metrics['max_ms']} ms")

        # Performance rating
        avg = metrics['avg_ms']
        if avg < 50:
            rating = "🚀 Excellent"
        elif avg < 200:
            rating = "✅ Good"
        elif avg < 500:
            rating = "⚠️ Fair"
        else:
            rating = "❌ Poor"
        print(f"  Rating: {rating}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--health":
            conn_string = os.environ.get("SQL_CONNECTION_STRING") or load_local_settings()
            if not conn_string:
                print("❌ ERROR: SQL_CONNECTION_STRING not found")
                sys.exit(1)

            health = test_database_health(conn_string)
            print_health_report(health)
            sys.exit(0 if health["status"] in ["healthy", "degraded"] else 1)

        elif sys.argv[1] == "--performance":
            conn_string = os.environ.get("SQL_CONNECTION_STRING") or load_local_settings()
            if not conn_string:
                print("❌ ERROR: SQL_CONNECTION_STRING not found")
                sys.exit(1)

            results = test_database_performance(conn_string)
            print_performance_report(results)
            sys.exit(0)

    # Default: run connection test
    success = test_connection()
    sys.exit(0 if success else 1)
