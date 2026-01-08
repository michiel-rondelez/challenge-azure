"""
Database connection test script
Run with: python tests/test_database.py
"""
import os
import sys
import pyodbc
from datetime import datetime

# Add parent directory to path so we can import from function_app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_connection():
    """Test basic database connection"""
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)

    # Get connection string from environment
    conn_string = os.environ.get("SQL_CONNECTION_STRING")

    if not conn_string:
        print("❌ ERROR: SQL_CONNECTION_STRING environment variable not set")
        print("\nSet it in your local.settings.json or environment:")
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

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
