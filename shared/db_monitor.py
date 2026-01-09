"""
Database monitoring and metrics collection
Integrates with Azure Application Insights for custom metrics
"""
import os
import logging
import pyodbc
from datetime import datetime
from typing import Dict, Any, Optional
from .db import get_db_connection


class DatabaseMonitor:
    """Monitor database health and collect metrics"""

    def __init__(self, telemetry_client=None):
        """
        Initialize database monitor

        Args:
            telemetry_client: Azure Application Insights telemetry client (optional)
        """
        self.telemetry_client = telemetry_client
        self.logger = logging.getLogger(__name__)

    def collect_metrics(self) -> Dict[str, Any]:
        """
        Collect all database metrics
        Returns dict with metrics that can be sent to Application Insights
        """
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "database": {},
            "tables": {},
            "performance": {}
        }

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Database size
            cursor.execute("""
                SELECT
                    SUM(size) * 8 / 1024.0 as size_mb
                FROM sys.master_files
                WHERE database_id = DB_ID()
            """)
            db_size = cursor.fetchone()[0]
            if db_size:
                metrics["database"]["size_mb"] = round(db_size, 2)
                if self.telemetry_client:
                    self.telemetry_client.track_metric("DatabaseSize_MB", db_size)

            # Active connections
            cursor.execute("""
                SELECT COUNT(*)
                FROM sys.dm_exec_sessions
                WHERE is_user_process = 1
            """)
            active_conns = cursor.fetchone()[0]
            metrics["database"]["active_connections"] = active_conns
            if self.telemetry_client:
                self.telemetry_client.track_metric("DatabaseActiveConnections", active_conns)

            # Table row counts
            for table in ["Stations", "Departures"]:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    metrics["tables"][f"{table.lower()}_count"] = count
                    if self.telemetry_client:
                        self.telemetry_client.track_metric(f"Table{table}Count", count)
                except:
                    pass

            # Data freshness (minutes since last departure fetch)
            cursor.execute("""
                SELECT DATEDIFF(MINUTE, MAX(fetched_at), GETDATE())
                FROM Departures
            """)
            row = cursor.fetchone()
            if row and row[0] is not None:
                minutes_since = row[0]
                metrics["tables"]["minutes_since_last_fetch"] = minutes_since
                if self.telemetry_client:
                    self.telemetry_client.track_metric("DataFreshness_Minutes", minutes_since)

            # Average delay statistics
            cursor.execute("""
                SELECT
                    AVG(CAST(delay AS FLOAT)) as avg_delay,
                    MAX(delay) as max_delay,
                    COUNT(*) as delayed_trains
                FROM Departures
                WHERE fetched_at > DATEADD(HOUR, -24, GETDATE())
                AND delay > 0
            """)
            row = cursor.fetchone()
            if row and row[2] > 0:
                metrics["tables"]["avg_delay_seconds_24h"] = round(row[0], 2) if row[0] else 0
                metrics["tables"]["max_delay_seconds_24h"] = row[1]
                metrics["tables"]["delayed_trains_24h"] = row[2]

                if self.telemetry_client:
                    self.telemetry_client.track_metric("AvgDelay_Seconds_24h", row[0] or 0)
                    self.telemetry_client.track_metric("MaxDelay_Seconds_24h", row[1])
                    self.telemetry_client.track_metric("DelayedTrains_24h", row[2])

            cursor.close()
            conn.close()

        except Exception as e:
            self.logger.error(f"Error collecting database metrics: {str(e)}")
            metrics["error"] = str(e)
            if self.telemetry_client:
                self.telemetry_client.track_exception()

        return metrics

    def check_health(self) -> Dict[str, Any]:
        """
        Perform health check and return status
        Returns dict with health status and any issues
        """
        health = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "issues": []
        }

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if tables exist
            cursor.execute("""
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME IN ('Stations', 'Departures')
            """)
            existing_tables = {row[0] for row in cursor.fetchall()}

            if "Stations" not in existing_tables:
                health["status"] = "unhealthy"
                health["issues"].append("Stations table missing")

            if "Departures" not in existing_tables:
                health["status"] = "unhealthy"
                health["issues"].append("Departures table missing")

            # Check data freshness
            if "Departures" in existing_tables:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        DATEDIFF(MINUTE, MAX(fetched_at), GETDATE()) as minutes_since
                    FROM Departures
                """)
                row = cursor.fetchone()

                if row[0] == 0:
                    health["status"] = "degraded"
                    health["issues"].append("No departure data in database")
                elif row[1] and row[1] > 30:
                    health["status"] = "degraded"
                    health["issues"].append(f"Data is stale ({row[1]} minutes since last fetch)")

            # Check stations data
            if "Stations" in existing_tables:
                cursor.execute("SELECT COUNT(*) FROM Stations")
                count = cursor.fetchone()[0]
                if count == 0:
                    health["status"] = "degraded"
                    health["issues"].append("No stations in database")

            cursor.close()
            conn.close()

            # Log health status
            if health["status"] != "healthy":
                self.logger.warning(f"Database health check: {health['status']} - {health['issues']}")
                if self.telemetry_client:
                    self.telemetry_client.track_event(
                        "DatabaseHealthDegraded",
                        properties={"status": health["status"], "issues": str(health["issues"])}
                    )

        except pyodbc.Error as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Database connection error: {str(e)}")
            self.logger.error(f"Database health check failed: {str(e)}")
            if self.telemetry_client:
                self.telemetry_client.track_exception()

        except Exception as e:
            health["status"] = "error"
            health["issues"].append(f"Health check error: {str(e)}")
            self.logger.error(f"Health check error: {str(e)}")
            if self.telemetry_client:
                self.telemetry_client.track_exception()

        return health

    def track_operation(self, operation_name: str, duration_ms: float,
                       success: bool, properties: Optional[Dict] = None):
        """
        Track a database operation for monitoring

        Args:
            operation_name: Name of the operation (e.g., "fetch_stations")
            duration_ms: Duration in milliseconds
            success: Whether operation succeeded
            properties: Additional properties to log
        """
        if self.telemetry_client:
            self.telemetry_client.track_metric(
                f"Operation_{operation_name}_Duration_ms",
                duration_ms
            )

            event_props = {
                "operation": operation_name,
                "success": str(success),
                "duration_ms": duration_ms
            }
            if properties:
                event_props.update(properties)

            self.telemetry_client.track_event(
                "DatabaseOperation",
                properties=event_props
            )

        if not success:
            self.logger.warning(
                f"Database operation failed: {operation_name} "
                f"(took {duration_ms}ms)"
            )
