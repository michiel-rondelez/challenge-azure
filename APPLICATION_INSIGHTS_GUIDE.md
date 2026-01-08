# Application Insights Guide for Train Data Function

## Overview

This guide explains how to use Application Insights with your Azure Functions project for monitoring, logging, and custom telemetry.

## What We've Added

### 1. **Enhanced Dependencies**
Added to [requirements.txt](requirements.txt):
```
opencensus-ext-azure       # Azure Application Insights integration
opencensus-ext-logging     # Enhanced logging capabilities
```

### 2. **Custom Metrics**
The function now tracks:
- **trains_fetched**: Number of trains successfully stored per station
- **api_response_time**: How long the iRail API takes to respond (in milliseconds)
- **train_delay_seconds**: Distribution of train delays by station

### 3. **Enhanced Logging**
Every operation now logs:
- API call initiation and response times
- Number of departures found
- Database insertion statistics
- Average delays and cancellation counts
- Execution duration for HTTP and Timer triggers

---

## How Application Insights Works

### Automatic Telemetry (Built-in)

When you enable Application Insights in Azure Portal, you **automatically** get:

1. **Request Tracking**: Every HTTP trigger call is logged with:
   - Request URL, method, status code
   - Execution duration
   - Success/failure status

2. **Dependency Tracking**: External calls are tracked:
   - SQL Database queries
   - HTTP requests to iRail API
   - Response times and status

3. **Exception Tracking**: All errors are captured with:
   - Stack traces
   - Error messages
   - Context (function name, timestamp)

4. **Performance Metrics**:
   - Function execution times
   - Memory usage
   - CPU utilization

### Custom Telemetry (What We Added)

The enhanced code adds **business-specific metrics**:
- How many trains were fetched per station
- API performance by station
- Train delay distributions for analysis
- Batch execution statistics

---

## Working with Application Insights in Azure Portal

### 1. **Access Application Insights**

1. Navigate to your Function App in Azure Portal
2. Click **Application Insights** in the left menu
3. You'll see the Overview dashboard with:
   - Failed requests
   - Server response time
   - Server requests count
   - Availability

### 2. **View Real-Time Logs (Live Metrics)**

**Path**: Function App → Application Insights → **Live Metrics**

**What you see**:
- Real-time function executions
- Incoming requests per second
- Outgoing dependency calls
- Live telemetry stream

**Use case**: Watch your function execute in real-time when testing

### 3. **Query Logs with KQL (Kusto Query Language)**

**Path**: Application Insights → **Logs**

#### Example Query 1: View All Function Executions
```kusto
traces
| where timestamp > ago(1h)
| where message contains "Fetching" or message contains "Successfully"
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc
```

#### Example Query 2: Track API Response Times
```kusto
traces
| where timestamp > ago(24h)
| where message contains "API response time"
| extend responseTime = extract(@"(\d+\.\d+)ms", 1, message)
| extend station = extract(@"for (.+)$", 1, message)
| project timestamp, station, responseTime_ms = todouble(responseTime)
| summarize avg(responseTime_ms), max(responseTime_ms) by station
```

#### Example Query 3: Find Errors and Exceptions
```kusto
exceptions
| where timestamp > ago(24h)
| project timestamp, type, outerMessage, problemId, operation_Name
| order by timestamp desc
```

#### Example Query 4: Monitor Timer Trigger Executions
```kusto
traces
| where timestamp > ago(7d)
| where message contains "SCHEDULED FETCH COMPLETED"
| extend totalRecords = extract(@"Total records inserted: (\d+)", 1, message)
| extend executionTime = extract(@"Total execution time: (\d+\.\d+)s", 1, message)
| project timestamp, totalRecords = toint(totalRecords), executionTime_seconds = todouble(executionTime)
| order by timestamp desc
```

#### Example Query 5: Track Train Delays by Station
```kusto
traces
| where timestamp > ago(24h)
| where message contains "Statistics - Avg delay"
| extend avgDelay = extract(@"Avg delay: (\d+)s", 1, message)
| extend cancelled = extract(@"Cancelled: (\d+)", 1, message)
| extend station = extract(@"for (.+)$", 1, message)
| project timestamp, station, avgDelay_seconds = toint(avgDelay), cancelled = toint(cancelled)
| summarize avg(avgDelay_seconds), sum(cancelled) by station
```

### 4. **View Custom Metrics**

**Path**: Application Insights → **Metrics**

1. Click **Add metric**
2. Select **Metric Namespace**: "azure.applicationinsights"
3. Select your custom metrics:
   - `trains_fetched`
   - `api_response_time`
   - `train_delay_seconds`
4. Add **Splits** by dimension (e.g., station)
5. Choose aggregation: Sum, Avg, Max, Min

**Create charts**:
- Line chart: API response time over time by station
- Bar chart: Total trains fetched per station
- Distribution: Train delay histogram

### 5. **Set Up Alerts**

**Path**: Application Insights → **Alerts** → **Create alert rule**

#### Example Alert 1: Function Failures
- **Condition**: `exceptions | count > 5` in 5 minutes
- **Action**: Send email to admin
- **Use case**: Get notified when function is failing

#### Example Alert 2: API Slow Response
- **Condition**: `traces | where message contains "API response time" | where responseTime > 5000ms`
- **Action**: Send notification
- **Use case**: Alert when iRail API is slow

#### Example Alert 3: No Data Collection
- **Condition**: No successful timer executions in last 2 hours
- **Action**: Send alert
- **Use case**: Detect when scheduled job stops running

### 6. **Application Map**

**Path**: Application Insights → **Application Map**

**What you see**:
- Visual representation of your function dependencies
- Nodes for: Function App, SQL Database, iRail API
- Success rates and response times on each connection
- Failed dependency calls highlighted in red

**Use case**: Quickly identify where failures occur in your pipeline

### 7. **Performance Analysis**

**Path**: Application Insights → **Performance**

**What you see**:
- Operation performance by function name
- Slowest operations
- Dependencies contributing to latency
- Drill into individual requests

**Use case**: Optimize slow functions

### 8. **Failures Blade**

**Path**: Application Insights → **Failures**

**What you see**:
- Failed requests over time
- Top 3 exception types
- Failed dependency calls
- Response codes (500, 503, etc.)

**Use case**: Debug production issues quickly

---

## Custom Metrics in Detail

### How Custom Metrics Work

The code uses OpenCensus to track custom business metrics:

```python
# Track number of trains fetched
mmap.measure_int_put(trains_fetched_measure, inserted)

# Track API response time
mmap.measure_float_put(api_response_time_measure, api_duration_ms)

# Track train delays
mmap.measure_int_put(delay_seconds_measure, delay_seconds)
```

### Query Custom Metrics

```kusto
customMetrics
| where name == "trains_fetched"
| extend station = tostring(customDimensions.station)
| summarize sum(value) by station, bin(timestamp, 1h)
| render timechart
```

---

## Local Development with Application Insights

### Option 1: Without Application Insights Locally
The code gracefully handles missing Application Insights:
```python
if APPINSIGHTS_AVAILABLE and APPINSIGHTS_CONNECTION_STRING:
    # Custom metrics enabled
else:
    # Falls back to basic logging only
```

**Local setup**: Just ensure the OpenCensus packages are **not** installed locally, or leave `APPLICATIONINSIGHTS_CONNECTION_STRING` empty in `local.settings.json`.

### Option 2: Test Application Insights Locally

1. Get the connection string from Azure:
   ```
   Portal → Application Insights → Overview → Connection String
   ```

2. Add to [local.settings.json](local.settings.json):
   ```json
   {
     "Values": {
       "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=...;IngestionEndpoint=..."
     }
   }
   ```

3. Install packages locally:
   ```bash
   pip install opencensus-ext-azure opencensus-ext-logging
   ```

4. Run function locally:
   ```bash
   func start
   ```

5. Check Azure Portal - your local runs will appear in Application Insights!

---

## Best Practices

### 1. **Use Structured Logging**
```python
# Good - structured and searchable
logging.info(f"Successfully inserted {count} records for {station}")

# Bad - unstructured
logging.info("Done")
```

### 2. **Log at Appropriate Levels**
- `logging.info()`: Normal operations (API calls, records inserted)
- `logging.warning()`: Unexpected but handled (no departures found)
- `logging.error()`: Failures requiring attention (API errors, DB failures)
- `logging.debug()`: Detailed troubleshooting (only when needed)

### 3. **Include Context in Logs**
```python
# Include station name, counts, timestamps
logging.info(f"Processing station {i+1}/{total}: {station}")
```

### 4. **Track Business Metrics**
Don't just track technical metrics - track what matters for analysis:
- Number of trains per station
- Average delays by time of day
- Cancellation rates
- API reliability per station

### 5. **Set Up Alerts**
Don't wait for users to report issues:
- Alert on function failures
- Alert on API timeout increases
- Alert when scheduled job stops running

### 6. **Regular Review**
Check Application Insights weekly:
- Review performance trends
- Identify optimization opportunities
- Check for new error patterns

---

## Troubleshooting

### Issue: "opencensus" modules not found in Azure

**Solution**: Ensure `opencensus-ext-azure` and `opencensus-ext-logging` are in [requirements.txt](requirements.txt) and redeploy.

### Issue: Custom metrics not appearing

**Solution**:
1. Check `APPLICATIONINSIGHTS_CONNECTION_STRING` is set in Application Settings
2. Wait 2-3 minutes for metrics to appear (not instant)
3. Check for exceptions in Logs blade

### Issue: Logs not showing in Application Insights

**Solution**:
1. Verify Application Insights is enabled for Function App
2. Check Function App → Configuration → `APPLICATIONINSIGHTS_CONNECTION_STRING` exists
3. Restart Function App
4. Wait a few minutes for telemetry to flow

### Issue: Too much logging / high costs

**Solution**:
1. Application Insights → Usage and estimated costs → Daily cap
2. Set sampling rate: Application Insights → Configure → Sampling (e.g., 50%)
3. Reduce log verbosity in code

---

## Cost Considerations

Application Insights pricing (as of 2026):
- **First 5 GB/month**: Free
- **Additional data**: ~$2.30 per GB

**Your function's typical usage**:
- Logs per execution: ~10 KB
- Hourly timer (4 stations): ~40 KB/hour = ~30 MB/month
- HTTP trigger usage: depends on how often you call it

**Estimated monthly cost**: $0 (well within free tier)

**Cost optimization**:
- Use sampling for high-volume apps
- Set data retention to 30-90 days (default is 90)
- Archive old logs to Storage Account (cheaper)

---

## Advanced: Workbooks and Dashboards

### Create Custom Dashboard

1. **Path**: Application Insights → **Workbooks** → **New**
2. Add visualizations:
   - Chart: Trains fetched over time by station
   - Grid: Recent errors and exceptions
   - Map: Station performance comparison
3. Save and share with team

### Example Workbook Queries

**Trains Fetched per Station (Last 7 Days)**:
```kusto
traces
| where timestamp > ago(7d)
| where message contains "Successfully inserted"
| extend station = extract(@"for (.+)$", 1, message)
| extend count = extract(@"inserted (\d+)", 1, message)
| summarize TotalTrains = sum(toint(count)) by station
| render barchart
```

**API Performance Trend**:
```kusto
traces
| where timestamp > ago(24h)
| where message contains "API response time"
| extend responseTime = extract(@"(\d+\.\d+)ms", 1, message)
| extend station = extract(@"for (.+)$", 1, message)
| project timestamp, station, responseTime_ms = todouble(responseTime)
| render timechart
```

---

## Summary

✅ **What you get automatically** (no code changes):
- Request/response tracking
- Dependency monitoring
- Exception tracking
- Performance metrics

✅ **What we added** (enhanced version):
- Custom business metrics (trains fetched, delays, API times)
- Detailed structured logging
- Station-level performance tracking
- Batch execution statistics

✅ **How to use it**:
- Monitor real-time with Live Metrics
- Query logs with KQL in Logs blade
- View custom metrics in Metrics blade
- Set up alerts for failures
- Analyze trends with Workbooks

✅ **Next steps**:
1. Deploy the enhanced function to Azure
2. Run a few test requests
3. Explore Application Insights in Portal
4. Set up your first alert
5. Create a custom dashboard

---

**Questions?** Check the [README.md](README.md) or review the deployment plan for more details.
