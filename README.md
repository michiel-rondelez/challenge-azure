# Belgian Train Data Pipeline - Azure Functions

Real-time Belgian train data collection using iRail API and Azure Functions.

## Architecture

```
iRail API → Azure Functions (HTTP + Timer) → Azure SQL Database
```

## Features

- **HTTP Trigger**: Manual station data queries via API endpoint
- **Timer Trigger**: Automated hourly data collection from 4 major Belgian stations
- **Normalized Storage**: Relational database with stations and departures tables
- **Rate Limiting**: Respects iRail API guidelines with request delays
- **Comprehensive Monitoring**: Health checks, metrics, alerts, and Application Insights integration
- **Modular Architecture**: Shared modules for database, API client, and monitoring

## Azure Resources

- **Function App**: Python 3.10 on Linux (Consumption Plan)
- **SQL Database**: TrainData
- **SQL Server**: traindata-server-michiel.database.windows.net

## Local Development Setup

### 1. Prerequisites

- **Python 3.10**: Ensure Python 3.10 is installed
- **Azure Functions Core Tools**: Install via:
  ```bash
  brew install azure-functions-core-tools@4  # macOS
  # Or download from: https://aka.ms/func
  ```
- **ODBC Driver 18 for SQL Server**: Required for database connections
  ```bash
  brew install unixodbc  # macOS
  ```

### 2. Clone and Setup

```bash
# Clone repository
git clone <your-repo-url>
cd challenge-azure

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Local Settings

Edit `local.settings.json` and add your database connection string:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "DEBUG": "1",
    "SQL_CONNECTION_STRING": "Driver={ODBC Driver 18 for SQL Server};Server=tcp:your-server.database.windows.net,1433;Database=TrainData;Uid=your-username;Pwd=your-password;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
  }
}
```

### 4. Test Database Connection

Before running the function, test your database connection:

**Quick Test (Recommended):**
```bash
# Run comprehensive health check
./scripts/quick-test.sh
```

**Full Test Suite:**
```bash
# Run all tests (connection, health, performance)
./scripts/run-tests.sh

# Run specific tests
./scripts/run-tests.sh --health        # Health check only
./scripts/run-tests.sh --performance   # Performance benchmark only
./scripts/run-tests.sh --connection    # Connection test only

# CI mode (exit on first failure)
./scripts/run-tests.sh --ci
```

**Manual Testing:**
```bash
# Basic connection test
python tests/test_database.py

# Health check with metrics
python tests/test_database.py --health

# Performance benchmark
python tests/test_database.py --performance
```

Expected output:
```
==========================================================
DATABASE HEALTH CHECK REPORT
==========================================================

Overall Status: ✅ HEALTHY
Timestamp: 2026-01-09T14:30:00

--- Health Checks ---
  ✅ connection: pass
  ✅ query_performance: pass
  ✅ stations_table: pass
  ✅ departures_table: pass
  ✅ data_freshness: pass

--- Metrics ---
  • connection_time_ms: 45.2
  • total_departures: 15432
  • total_stations: 687
  • minutes_since_last_fetch: 8
  • database_size_mb: 124.5
==========================================================
```

### 5. Run Locally

**Start the function:**
```bash
source venv/bin/activate
func start
```

**Test the HTTP endpoint:**
```bash
# In another terminal
curl http://localhost:7071/api/fetch_trains

# Or with a specific station
curl "http://localhost:7071/api/fetch_trains?station=Antwerp-Central"

# Or open in browser
open http://localhost:7071/api/fetch_trains
```

Expected response:
```
Inserted 18 records for Brussels-Central
```

### 6. Debug with VSCode

**Enable debug mode:**
```bash
source venv/bin/activate
DEBUG=1 func start
```

Wait for this message:
```
Debugpy listening on port 5678
```

**Attach debugger:**
1. Open VSCode
2. Press `Cmd+Shift+D` (Run and Debug)
3. Select **"Attach to Python Functions"**
4. Click the green play button (F5)
5. Set breakpoints in `function_app.py` by clicking left margin
6. Trigger the function with curl or browser

**Debug controls:**
- **F5**: Continue to next breakpoint
- **F10**: Step over (execute current line)
- **F11**: Step into (enter function calls)
- **Shift+F11**: Step out (exit current function)
- **Shift+F5**: Stop debugging

**Common breakpoint locations:**
- Line 78: `def fetch_trains_http(...)` - Function entry
- Line 80: `count = fetch_and_store_trains(station)` - Before main logic
- Line 42: `res = requests.get(...)` - Before API call
- Line 54: `station_id = get_or_create_station(...)` - Database operation

## Deployment to Azure

### Prerequisites
- Azure for Students account
- SQL Database with stations and departures tables already created
- VS Code with Azure Functions extension installed

### Quick Deployment Steps

1. **Create Function App** in Azure Portal
   - Runtime: Python 3.10
   - Plan: Consumption (Serverless)

2. **Configure Application Settings with Key Vault Reference**

   If you're using Azure Key Vault to store your SQL connection string:

   - Go to your Function App → **Configuration** → **Application settings**
   - Add new setting:
     - **Name**: `SQL_CONNECTION_STRING`
     - **Value**: `@Microsoft.KeyVault(SecretUri=https://your-keyvault.vault.azure.net/secrets/sql-connection-string/)`

   Or use this format with secret name only:
   ```
   @Microsoft.KeyVault(VaultName=your-keyvault;SecretName=sql-connection-string)
   ```

   **Enable Managed Identity:**
   - Go to Function App → **Identity** → **System assigned**
   - Turn **Status** to **On** and click **Save**
   - Copy the **Object (principal) ID**

   **Grant Key Vault Access:**
   - Go to Key Vault → **Access policies** → **Create**
   - Select permissions: **Get** (under Secret permissions)
   - Select principal: Paste the Function App's Object ID
   - Click **Review + create**

   Alternative (direct connection string):
   - Add `SQL_CONNECTION_STRING` with your database connection string directly
   - Less secure but simpler for development

3. **Deploy via VS Code**
   - Open Command Palette (Cmd+Shift+P / Ctrl+Shift+P)
   - Select "Azure Functions: Deploy to Function App"
   - Choose your Function App
   - Wait for deployment to complete (2-3 minutes)

4. **Verify SQL Firewall**
   - Enable "Allow Azure services and resources to access this server"

5. **Test Deployment**
   - Test HTTP trigger endpoint
   - Verify data in SQL Database
   - Monitor Timer trigger executions

For detailed step-by-step instructions, see the deployment plan: `.claude/plans/harmonic-strolling-sedgewick.md`

## API Usage

### HTTP Trigger - Manual Fetch

**Endpoint:**
```
GET https://<your-app>.azurewebsites.net/api/fetch_trains?station=Brussels-Central&code=<function_key>
```

**Parameters:**
- `station` (optional): Station name (default: "Brussels-Central")

**Response:**
```json
{
  "status": "success",
  "station": "Brussels-Central",
  "records_inserted": 18
}
```

**Example with curl:**
```bash
curl "https://<your-app>.azurewebsites.net/api/fetch_trains?station=Antwerp-Central&code=<key>"
```

### Timer Trigger - Automated Collection

- **Schedule**: Every hour at :00 minutes (cron: `0 0 * * * *`)
- **Stations**: Brussels-Central, Antwerp-Central, Ghent-Sint-Pieters, Brussels-South
- **Execution**: Automatic, no manual invocation needed

## Monitoring & Health Checks

This project includes comprehensive monitoring capabilities. See [MONITORING.md](MONITORING.md) for detailed documentation.

### Quick Health Check

```bash
# Run comprehensive health check
python tests/test_database.py --health

# Run performance benchmark
python tests/test_database.py --performance
```

### Key Monitoring Features

- **Automated Health Checks**: Monitor database connectivity, data freshness, and table status
- **Custom Metrics**: Track database size, connection count, delay statistics, and more
- **Alert Rules**: Automated alerts for high DTU usage, failed connections, stale data, etc.
- **Application Insights**: Pre-built KQL queries for performance analysis
- **Performance Testing**: Benchmark database operations

### Viewing Monitoring

- **Monitoring**: Check Application Insights in Azure Portal for custom metrics and logs
- **Metrics Available**: Database size, connection count, data freshness, delay statistics
- **Health Checks**: Run `python tests/test_database.py --health` for manual checks

### Stations Management

**Fetch All Stations (HTTP only):**
```
GET https://<your-app>.azurewebsites.net/api/fetch_stations?code=<function_key>
```
- Fetches all Belgian train stations from iRail API
- Upserts stations into database with coordinates
- Returns: Count of processed stations

**Example:**
```bash
curl "https://<your-app>.azurewebsites.net/api/fetch_stations?code=<key>"
# Response: "Successfully processed 600 stations"
```

**Local testing:**
```bash
curl http://localhost:7071/api/fetch_stations
```

### Liveboard Collection

**Fetch All Liveboards (HTTP):**
```
GET https://<your-app>.azurewebsites.net/api/fetch_all_liveboards?code=<function_key>
```
- Fetches liveboard data for ALL stations in database
- Inserts departures into Departures table
- Returns: Count of departure records inserted

**Fetch All Liveboards (Scheduled):**
- **Schedule**: Every 15 minutes (cron: `0 */15 * * * *`)
- **Behavior**: Iterates through all stations and fetches their liveboards
- **Rate Limiting**: 0.5 second delay between stations
- **Execution**: Automatic, no manual invocation needed

**Example:**
```bash
curl "https://<your-app>.azurewebsites.net/api/fetch_all_liveboards?code=<key>"
# Response: "Successfully inserted 12458 departure records"
```

**Local testing:**
```bash
curl http://localhost:7071/api/fetch_all_liveboards
```

## Database Schema

### `stations` Table
| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key (auto-increment) |
| name | NVARCHAR | Station display name |
| standard_name | NVARCHAR | iRail standard name |
| location_x | FLOAT | Longitude coordinate |
| location_y | FLOAT | Latitude coordinate |
| irail_id | NVARCHAR(50) | iRail station identifier |
| created_at | DATETIME | Record creation timestamp |

### `departures` Table
| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key (auto-increment) |
| station_id | INT | Foreign key → stations.id |
| train_id | NVARCHAR | Unique train identifier |
| vehicle | NVARCHAR | Train type (IC, S, etc.) |
| platform | NVARCHAR | Departure platform |
| scheduled_time | DATETIME | Scheduled departure time |
| delay_seconds | INT | Delay in seconds |
| is_cancelled | BIT | Cancellation status |
| direction | NVARCHAR | Destination station |
| fetch_timestamp | DATETIME | Data collection timestamp |
| platform_normal | BIT | Platform normality flag |
| has_left | BIT | Train departure status |
| occupancy | NVARCHAR | Train occupancy level |

## Testing

**Run all tests:**
```bash
pytest tests/ -v
```

**Run with coverage:**
```bash
pytest tests/ -v --cov=. --cov-report=term-missing
```

**Current test coverage:** Minimal (1 unit test) - expansion recommended

## Project Structure

```
challenge-azure/
├── function_app.py              # Main Azure Functions code
├── host.json                    # Azure Functions runtime config
├── requirements.txt             # Python dependencies
├── requirements-dev.txt         # Development dependencies
├── local.settings.json          # Local environment vars (not committed)
├── local.settings.json.template # Template for local setup
├── .funcignore                  # Deployment exclusions
├── .gitignore                   # Git exclusions
├── tests/
│   ├── __init__.py
│   └── test_simple.py          # Unit tests
└── README.md                    # This file
```

## Monitoring and Troubleshooting

### View Logs in Azure Portal

1. Navigate to Function App → **Monitor** → **Logs**
2. Or use Log stream: Function App → **Log stream**
3. View execution history: Function App → Functions → Your function → **Monitor**

### Common Issues

| Issue | Solution |
|-------|----------|
| "requirements not found" | Verify file named `requirements.txt` (plural) |
| 500 Error - SQL Connection | Check SQL firewall allows Azure services |
| 401 Unauthorized | Include `?code=` parameter in URL |
| Timer not running | Check function is enabled in Portal |

### Check Function Execution

- **HTTP Trigger**: Test via Portal "Code + Test" tab
- **Timer Trigger**: View execution history in Monitor tab
- **Database**: Query departures table to verify data

## Data Analysis Use Cases

This pipeline enables various analytical scenarios:

- **Live Departure Board**: Display current/recent departures for selected stations
- **Delay Analysis**: Track which stations/trains have most delays over time
- **Peak Hour Patterns**: Analyze train traffic and delays by time of day
- **Train Type Distribution**: Visualize where different train types operate
- **Cancellation Tracking**: Monitor cancellation frequencies by station

## Future Enhancements (Nice-to-Have)

### Power BI Dashboard
- [ ] Connect Power BI Desktop to Azure SQL Database
- [ ] Create visualizations: departure frequency, delay patterns
- [ ] Publish to Power BI Service with scheduled refresh

### Enhanced Data Collection
- [ ] Expand to more Belgian stations (60+ available)
- [ ] Add connections API (routes between cities)
- [ ] Collect vehicle composition data

### Monitoring & Alerts
- [ ] Email alerts for function failures
- [ ] Dashboard showing API success rate

### Data Management
- [ ] Implement data retention policies
- [ ] Add data quality checks
- [ ] Anomaly detection for unusual delays

## Security Considerations

**Current Implementation (Acceptable for Must-Have):**
- Connection strings stored in Application Settings
- Function-level authentication for HTTP trigger
- SQL authentication with username/password

**Production Improvements:**
1. **Azure Managed Identity**: SQL authentication without passwords
2. **Azure Key Vault**: Store connection strings as secrets
3. **Input Validation**: Sanitize station parameter for SQL injection protection
4. **Function Key Rotation**: Regularly update API keys

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is part of the BeCode AI/Data training program.

## Acknowledgments

- **iRail API**: https://api.irail.be/ - Belgian railway data provider
- **Azure Functions**: Serverless compute platform
- **BeCode**: Training provider for Azure challenge

## Support

For issues or questions:
- Check the troubleshooting section above
- Review function logs in Azure Portal (Monitor → Logs)
- Consult the detailed deployment plan in `.claude/plans/`

---

**Project Status**: Must-Have Level Complete ✓

Last Updated: 2026-01-08
