# SQLAlchemy Transaction Guide

## Understanding Engine, Session, Flush, and Commit

### Key Concepts

1. **Engine** - Manages a pool of database connections (created once, reused)
2. **Session** - Manages a conversation with the database (borrows connection from pool)
3. **flush()** - Sends SQL to database but doesn't commit
4. **commit()** - Permanently saves all changes
5. **rollback()** - Undoes all changes since last commit
6. **close()** - Returns connection to pool (doesn't close it)

---

## The Engine and Connection Pool

### What is the Engine?

The **Engine** is SQLAlchemy's connection manager:

```
┌────────────────────────────────────────┐
│           Your Application              │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │         Engine                    │ │
│  │  (Created once, reused forever)  │ │
│  │                                   │ │
│  │  ┌─────────────────────────────┐ │ │
│  │  │   Connection Pool (5 conns) │ │ │
│  │  │   [●] [●] [●] [●] [●]       │ │ │
│  │  └─────────────────────────────┘ │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
         │         │         │
         ▼         ▼         ▼
    ┌─────────────────────────────┐
    │   Azure SQL Database        │
    └─────────────────────────────┘
```

### How Connection Pooling Works

**Without Connection Pooling (Slow):**
```python
# Request 1
conn = create_new_connection()  # 100ms - slow!
execute_query(conn)
close_connection(conn)

# Request 2
conn = create_new_connection()  # 100ms - slow!
execute_query(conn)
close_connection(conn)

# Total: 200ms just for connections!
```

**With Connection Pooling (Fast):**
```python
# Setup (once)
engine = create_engine(...)  # Creates pool with 5 connections

# Request 1
session = get_session()  # Borrows from pool - instant!
execute_query(session)
session.close()  # Returns to pool (doesn't close)

# Request 2
session = get_session()  # Reuses same connection - instant!
execute_query(session)
session.close()  # Returns to pool

# Total: ~0ms for connections!
```

### Connection Pool Lifecycle

```python
# 1. Create engine (happens once at startup)
engine = create_engine("mssql+pyodbc://...")
# → Creates pool with 5 connections
# → Connections are opened lazily (when first needed)

# 2. Create session (happens per request)
session = get_session()
# → Borrows connection from pool
# → If all 5 busy, waits for one to become free

# 3. Use session
session.add(station)
session.commit()

# 4. Close session (happens at end of request)
session.close()
# → Returns connection to pool (doesn't close it!)
# → Connection sits in pool, ready for next request

# 5. Connection is reused
session2 = get_session()
# → Gets the SAME physical connection from pool
# → Very fast - no new connection needed
```

### Why Connection Pooling Matters

**Performance Impact:**
- Creating new connection: 50-100ms
- Borrowing from pool: <1ms
- **100x faster!**

**Resource Usage:**
- Without pool: Creates/closes connections constantly
- With pool: Reuses 5 connections indefinitely
- Reduces load on database server

### Connection Pool Settings

```python
# Default pool (5 connections)
engine = create_engine(url)

# Custom pool size
engine = create_engine(
    url,
    pool_size=10,        # Keep 10 connections in pool
    max_overflow=20,     # Allow 20 more if needed (total: 30)
    pool_pre_ping=True   # Check if connection alive before using
)
```

---

## How Session Uses the Engine

## Transaction Lifecycle

```python
session = get_session()  # ← Transaction starts here automatically

# Make changes
station = StationModel(name="Test")
session.add(station)

session.flush()   # ← Executes INSERT, generates ID, but NOT committed
                  # Changes are visible in this session only
                  # Can still rollback!

session.commit()  # ← PERMANENTLY saves to database
                  # Changes are now visible to all other sessions
                  # Cannot rollback after this point

session.close()   # ← Release database connection
```

---

## Example 1: Successful Transaction

```python
session = get_session()
try:
    # Insert 10 stations
    for i in range(10):
        station = StationModel(name=f"Station {i}")
        session.add(station)
        session.flush()  # Get ID immediately
        print(f"Station {station.id} created (not committed yet)")

    session.commit()  # ✓ All 10 stations saved permanently
    print("Success! All stations committed.")

except Exception as e:
    session.rollback()  # Won't execute (no error occurred)
    print(f"Error: {e}")

finally:
    session.close()

# Result: All 10 stations are in the database
```

---

## Example 2: Transaction with Rollback

```python
session = get_session()
try:
    # Insert 5 stations successfully
    for i in range(5):
        station = StationModel(name=f"Station {i}")
        session.add(station)
        session.flush()
        print(f"Station {station.id} created")

    # ERROR occurs here (e.g., network failure, invalid data)
    raise ValueError("Something went wrong!")

    session.commit()  # Never reached!

except Exception as e:
    session.rollback()  # ✗ UNDO everything!
    print(f"Error occurred: {e}")
    print("All changes rolled back - no stations saved")

finally:
    session.close()

# Result: ZERO stations in database (all rolled back)
```

---

## Example 3: What flush() Does

```python
session = get_session()

# Add station but don't flush
station1 = StationModel(name="Brussels")
session.add(station1)
print(station1.id)  # → None (ID not generated yet)

# Flush to get the ID
session.flush()
print(station1.id)  # → 123 (ID generated!)

# But it's NOT committed yet!
# If we rollback now, station won't be saved
session.rollback()  # Undoes the insert
print("Station was not saved")

session.close()
```

---

## Example 4: Real-World Pattern (Like Our Code)

```python
def fetch_and_store_all_liveboards():
    """Fetch data for multiple stations"""
    session = None
    try:
        session = get_session()  # Start transaction

        for station in stations:
            # Fetch departures for this station
            departures = api.fetch_liveboard(station)

            for dep in departures:
                session.add(dep)
                session.flush()  # Write to DB, get IDs

        # If we get here, everything worked!
        session.commit()  # Save ALL stations permanently
        print("✓ All stations committed")

    except Exception as e:
        # Error in ANY station? Rollback EVERYTHING
        if session:
            session.rollback()
        print(f"✗ Error: {e}. ALL changes rolled back")
        return 0

    finally:
        if session:
            session.close()  # Always cleanup
```

---

## When Does Rollback Happen?

### Automatic Rollback
1. **Exception occurs** and you call `session.rollback()`
2. **Session is closed** without commit (implicit rollback)
3. **Connection lost** to database

### Manual Rollback
```python
session = get_session()
station = StationModel(name="Test")
session.add(station)
session.flush()

# Changed my mind!
session.rollback()  # Undo the insert
session.close()
```

---

## flush() vs commit()

| Operation | flush() | commit() |
|-----------|---------|----------|
| Sends SQL to DB | ✓ Yes | ✓ Yes |
| Generates IDs | ✓ Yes | ✓ Yes |
| Permanently saves | ✗ No | ✓ Yes |
| Can rollback | ✓ Yes | ✗ No |
| Visible to other sessions | ✗ No | ✓ Yes |
| Ends transaction | ✗ No | ✓ Yes |

---

## Important Notes

1. **Always use try/except/finally** for proper error handling
2. **Call commit()** only when everything succeeds
3. **Call rollback()** in the except block to undo changes
4. **Call close()** in the finally block to cleanup
5. **flush() is optional** - commit() will flush automatically
6. **Use flush() when you need the ID** before committing

---

## Common Pitfall: Forgetting to Commit

```python
session = get_session()
station = StationModel(name="Test")
session.add(station)
session.flush()  # Writes to DB, gets ID
session.close()  # ← OOPS! Never committed!

# Result: Station NOT in database (implicit rollback on close)
```

**Fix:**
```python
session = get_session()
station = StationModel(name="Test")
session.add(station)
session.commit()  # ← Permanently saved
session.close()

# Result: Station IS in database ✓
```
