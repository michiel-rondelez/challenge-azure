# Shared Module Documentation

This directory contains shared utilities, models, and business logic used across all Azure Functions.

## Module Overview

### `models.py` - Data Models

Defines the core data structures for the application.

#### Station Model

```python
from shared.models import Station

# Create from API response
station = Station.from_api(api_data)

# Create from database row
station = Station.from_db_row(cursor_row)

# Access properties
print(station.name)              # "Brussels-Central"
print(station.standard_name)     # "Brussel-Centraal"
print(station.location_x)        # 4.421101 (longitude)
print(station.location_y)        # 51.2172 (latitude)
print(station.irail_id)          # "BE.NMBS.008821006"
```

#### Departure Model

```python
from shared.models import Departure

# Create from API response
departure = Departure.from_api(liveboard_data, station_id=123)

# Access properties
print(departure.train_id)        # "BE.NMBS.IC3033"
print(departure.vehicle)         # "IC3033"
print(departure.platform)        # "4"
print(departure.scheduled_time)  # datetime object
print(departure.delay)           # 120 (seconds)
print(departure.direction)       # "Antwerp-Central"
```

---

### `db.py` - Database Operations

Provides repository pattern for database operations.

#### Connection Management

```python
from shared.db import get_db_connection

# Get a database connection
conn = get_db_connection()
cursor = conn.cursor()

# Use cursor for queries
# ...

conn.commit()
conn.close()
```

#### StationRepository

```python
from shared.db import StationRepository, get_db_connection
from shared.models import Station

conn = get_db_connection()
cursor = conn.cursor()

# Upsert station (insert or update)
station = Station(name="Brussels-Central", standard_name="Brussel-Centraal")
station_id = StationRepository.upsert(cursor, station)

# Get or create simple (without coordinates)
station_id = StationRepository.get_or_create_simple(cursor, "Brussels-Central")

# Get all stations
stations = StationRepository.get_all(cursor)

# Get by ID
station = StationRepository.get_by_id(cursor, station_id=123)

conn.commit()
conn.close()
```

#### DepartureRepository

```python
from shared.db import DepartureRepository, get_db_connection
from shared.models import Departure

conn = get_db_connection()
cursor = conn.cursor()

# Insert single departure
departure = Departure(station_id=123, train_id="IC3033", ...)
DepartureRepository.insert(cursor, departure)

# Insert multiple departures
departures = [departure1, departure2, departure3]
count = DepartureRepository.insert_batch(cursor, departures)

# Get recent departures (last 60 minutes)
recent = DepartureRepository.get_recent(cursor, minutes=60, limit=100)

# Get departures for specific station
station_deps = DepartureRepository.get_by_station(cursor, station_id=123, limit=50)

conn.commit()
conn.close()
```

#### Decorator for Connection Management

```python
from shared.db import execute_with_connection

@execute_with_connection
def my_db_function(cursor, param1, param2):
    # Function receives cursor automatically
    cursor.execute("SELECT * FROM Stations WHERE name = ?", (param1,))
    return cursor.fetchall()
    # Connection is committed and closed automatically

# Usage
results = my_db_function("Brussels-Central", "some_param")
```

---

### `irail_client.py` - iRail API Client

Handles all interactions with the iRail API.

#### Basic Usage

```python
from shared.irail_client import IRailClient

# Create client
client = IRailClient()

# Fetch all stations
stations = client.fetch_all_stations()
for station in stations:
    print(f"{station.name} at ({station.location_x}, {station.location_y})")

# Fetch liveboard for a station (returns raw API data)
departures_data = client.fetch_liveboard("Brussels-Central")

# Fetch liveboard as Departure models
departures = client.fetch_liveboard_as_models("Brussels-Central", station_id=123)
```

#### Custom Timeout

```python
# Create client with custom timeout
client = IRailClient(timeout=20)  # 20 second timeout
```

#### API Response Handling

The client automatically handles:
- HTTP errors
- Request timeouts
- JSON parsing
- Logging of errors

Returns `None` or empty list on error, allowing graceful degradation.

---

## Usage Examples

### Complete Station Sync Flow

```python
from shared.irail_client import IRailClient
from shared.db import get_db_connection, StationRepository

# Fetch from API
client = IRailClient()
stations = client.fetch_all_stations()

# Store in database
conn = get_db_connection()
cursor = conn.cursor()

for station in stations:
    station_id = StationRepository.upsert(cursor, station)
    print(f"Processed: {station.name} (ID: {station_id})")

conn.commit()
conn.close()
```

### Complete Liveboard Sync Flow

```python
from shared.irail_client import IRailClient
from shared.db import get_db_connection, StationRepository, DepartureRepository

client = IRailClient()
conn = get_db_connection()
cursor = conn.cursor()

# Get all stations
stations = StationRepository.get_all(cursor)

# Fetch liveboards for each
for station in stations:
    departures = client.fetch_liveboard_as_models(station.name, station.id)
    count = DepartureRepository.insert_batch(cursor, departures)
    print(f"Inserted {count} departures for {station.name}")

conn.commit()
conn.close()
```

---

## Design Principles

### Repository Pattern
- Encapsulates all database operations
- Provides clean interface for data access
- Makes testing easier (can mock repositories)

### Model Objects
- Type-safe data structures using `@dataclass`
- Conversion methods for API and database data
- Self-documenting code

### API Client
- Single point of contact with external API
- Handles errors gracefully
- Respects rate limits and best practices

### Separation of Concerns
- **Models**: Data structures only
- **DB**: Database operations only
- **API Client**: External API calls only
- **Functions**: Orchestration and Azure Functions integration

---

## Testing

Each module can be tested independently:

```python
# Test models
from shared.models import Station
station = Station.from_api({"name": "Test", "standardname": "Test"})
assert station.name == "Test"

# Test database operations (requires connection)
from shared.db import StationRepository
# ... test with actual or mock database

# Test API client (can mock requests)
from shared.irail_client import IRailClient
# ... test with mock requests
```

---

## Best Practices

1. **Always use repositories** for database operations - don't write raw SQL in function code
2. **Always use models** - don't pass around dictionaries
3. **Use the API client** - don't make direct requests to iRail API
4. **Handle errors gracefully** - all functions can return None/empty lists
5. **Use type hints** - helps with IDE autocomplete and catches errors early

---

## Adding New Functionality

### New Database Operation

1. Add method to appropriate repository in `db.py`
2. Use models for parameters and return values
3. Document with docstring

### New API Endpoint

1. Add method to `IRailClient` in `irail_client.py`
2. Return model objects or raw data as appropriate
3. Handle errors and logging

### New Model

1. Add `@dataclass` to `models.py`
2. Implement `from_api()` and `from_db_row()` class methods
3. Document fields

---

## Import Guide

```python
# Models
from shared.models import Station, Departure

# Database
from shared.db import (
    get_db_connection,
    StationRepository,
    DepartureRepository,
    execute_with_connection
)

# API Client
from shared.irail_client import IRailClient
```
