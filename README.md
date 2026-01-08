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
- **Monitoring**: Application Insights integration for logs and metrics

## Azure Resources

- **Function App**: Python 3.10 on Linux (Consumption Plan)
- **SQL Database**: TrainData
- **SQL Server**: traindata-server-michiel.database.windows.net
- **Application Insights**: Enabled for monitoring and diagnostics

## Local Development Setup

1. **Clone repository**
   ```bash
   git clone <your-repo-url>
   cd challenge-azure
   ```

2. **Install Python 3.10**
   - Ensure Python 3.10 is installed on your system

3. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # For testing
   ```

5. **Configure local settings**
   ```bash
   cp local.settings.json.template local.settings.json
   ```
   Edit `local.settings.json` with your actual SQL credentials

6. **Run locally**
   ```bash
   func start
   ```

## Deployment to Azure

### Prerequisites
- Azure for Students account
- SQL Database with stations and departures tables already created
- VS Code with Azure Functions extension installed

### Quick Deployment Steps

1. **Create Function App** in Azure Portal
   - Runtime: Python 3.10
   - Plan: Consumption (Serverless)
   - Enable Application Insights

2. **Configure Application Settings**
   - Add `SQL_CONNECTION_STRING` with your database connection string

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
- **Monitoring**: Check Monitor tab in Azure Portal

## Database Schema

### `stations` Table
| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| name | NVARCHAR | Station display name |
| standardname | NVARCHAR | iRail standard name |

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

1. Navigate to Function App → **Application Insights**
2. Click **Logs** under Monitoring
3. Run KQL query:
   ```kusto
   traces
   | where timestamp > ago(2h)
   | where message contains "Fetching" or message contains "Successfully"
   | project timestamp, message, severityLevel
   | order by timestamp desc
   ```

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
- [ ] Custom Application Insights metrics
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
- Review Application Insights logs in Azure Portal
- Consult the detailed deployment plan in `.claude/plans/`

---

**Project Status**: Must-Have Level Complete ✓

Last Updated: 2026-01-08
