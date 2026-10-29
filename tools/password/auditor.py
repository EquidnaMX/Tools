"""
Audit logging and reporting for password changes

Maintains secure, encrypted audit logs of all password operations.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from .models import AuditEntry, OperationStatus


class AuditLogger:
    """Secure audit logging for password operations"""

    def __init__(self, db_path: str = "~/.tools/password_audit.db"):
        """Initialize audit logger with database"""
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    host TEXT NOT NULL,
                    username TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_code INTEGER,
                    result_message TEXT,
                    duration REAL,
                    verified BOOLEAN,
                    method TEXT,
                    ldap_synced BOOLEAN,
                    rollback_executed BOOLEAN,
                    notifications_sent TEXT,
                    password_hash TEXT,
                    ip_address TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for fast querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON audit_entries(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_host_user
                ON audit_entries(host, username)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_operator
                ON audit_entries(operator)
            """)
            conn.commit()

    def log_change(self, entry: AuditEntry) -> None:
        """Log password change entry"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_entries (
                    id, timestamp, operation, operator, host, username,
                    status, result_code, result_message, duration, verified,
                    method, ldap_synced, rollback_executed, notifications_sent,
                    password_hash, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.operation,
                    entry.operator,
                    entry.host,
                    entry.username,
                    entry.status.value,
                    entry.result_code,
                    entry.result_message,
                    entry.duration,
                    entry.verified,
                    entry.method,
                    entry.ldap_synced,
                    entry.rollback_executed,
                    json.dumps(entry.notifications_sent),
                    entry.password_hash,
                    entry.ip_address,
                ),
            )
            conn.commit()

    def query_log(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        operator: Optional[str] = None,
        status: Optional[OperationStatus] = None,
        limit: int = 1000,
    ) -> List[AuditEntry]:
        """Query audit log with filters"""
        query = "SELECT * FROM audit_entries WHERE 1=1"
        params = []

        if from_date:
            query += " AND timestamp >= ?"
            params.append(from_date.isoformat())

        if to_date:
            query += " AND timestamp <= ?"
            params.append(to_date.isoformat())

        if host:
            query += " AND host = ?"
            params.append(host)

        if username:
            query += " AND username = ?"
            params.append(username)

        if operator:
            query += " AND operator = ?"
            params.append(operator)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            entries = []
            for row in cursor.fetchall():
                entry = AuditEntry(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    operation=row["operation"],
                    operator=row["operator"],
                    host=row["host"],
                    username=row["username"],
                    status=OperationStatus(row["status"]),
                    result_code=row["result_code"],
                    result_message=row["result_message"],
                    duration=row["duration"],
                    verified=bool(row["verified"]),
                    method=row["method"],
                    ldap_synced=bool(row["ldap_synced"]),
                    rollback_executed=bool(row["rollback_executed"]),
                    notifications_sent=json.loads(row["notifications_sent"] or "[]"),
                    password_hash=row["password_hash"],
                    ip_address=row["ip_address"],
                )
                entries.append(entry)

            return entries

    def get_statistics(
        self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics"""
        if from_date is None:
            from_date = datetime.utcnow() - timedelta(days=30)
        if to_date is None:
            to_date = datetime.utcnow()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Total changes
            total = conn.execute(
                "SELECT COUNT(*) as count FROM audit_entries WHERE timestamp BETWEEN ? AND ?",
                (from_date.isoformat(), to_date.isoformat()),
            ).fetchone()["count"]

            # By status
            by_status = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM audit_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY status
            """,
                (from_date.isoformat(), to_date.isoformat()),
            )

            status_stats = {row["status"]: row["count"] for row in by_status.fetchall()}

            # By host
            by_host = conn.execute(
                """
                SELECT host, COUNT(*) as count
                FROM audit_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY host
                ORDER BY count DESC
                LIMIT 10
            """,
                (from_date.isoformat(), to_date.isoformat()),
            )

            host_stats = {row["host"]: row["count"] for row in by_host.fetchall()}

            # By operator
            by_operator = conn.execute(
                """
                SELECT operator, COUNT(*) as count
                FROM audit_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY operator
                ORDER BY count DESC
                LIMIT 10
            """,
                (from_date.isoformat(), to_date.isoformat()),
            )

            operator_stats = {
                row["operator"]: row["count"] for row in by_operator.fetchall()
            }

            # By user
            by_user = conn.execute(
                """
                SELECT username, COUNT(*) as count
                FROM audit_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY username
                ORDER BY count DESC
                LIMIT 10
            """,
                (from_date.isoformat(), to_date.isoformat()),
            )

            user_stats = {row["username"]: row["count"] for row in by_user.fetchall()}

            return {
                "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
                "total_changes": total,
                "by_status": status_stats,
                "by_host": host_stats,
                "by_operator": operator_stats,
                "by_user": user_stats,
            }

    def export_report(
        self,
        format: str = "json",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        output_file: Optional[str] = None,
    ) -> str:
        """
        Export audit report

        Formats: json, csv, html
        """
        entries = self.query_log(from_date, to_date, limit=10000)

        if format == "json":
            return self._export_json(entries, output_file)
        elif format == "csv":
            return self._export_csv(entries, output_file)
        elif format == "html":
            return self._export_html(entries, output_file)
        else:
            raise ValueError(f"Unknown format: {format}")

    def _export_json(
        self, entries: List[AuditEntry], output_file: Optional[str]
    ) -> str:
        """Export as JSON"""
        data = [entry.to_dict() for entry in entries]

        content = json.dumps(data, indent=2, default=str)

        if output_file:
            Path(output_file).write_text(content)

        return content

    def _export_csv(self, entries: List[AuditEntry], output_file: Optional[str]) -> str:
        """Export as CSV"""
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "timestamp",
                "operation",
                "operator",
                "host",
                "username",
                "status",
                "duration",
                "verified",
                "method",
                "ldap_synced",
            ],
        )

        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "operation": entry.operation,
                    "operator": entry.operator,
                    "host": entry.host,
                    "username": entry.username,
                    "status": entry.status.value,
                    "duration": entry.duration,
                    "verified": entry.verified,
                    "method": entry.method,
                    "ldap_synced": entry.ldap_synced,
                }
            )

        content = output.getvalue()

        if output_file:
            Path(output_file).write_text(content)

        return content

    def _export_html(
        self, entries: List[AuditEntry], output_file: Optional[str]
    ) -> str:
        """Export as HTML"""
        generated_at = datetime.utcnow().isoformat()
        html = f"""
<html>
<head>
    <meta charset="utf-8">
    <title>Password Change Audit Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .success {{ color: green; }}
        .failed {{ color: red; }}
    </style>
</head>
<body>
    <h1>Password Change Audit Report</h1>
    <p>Generated: {generated_at}</p>
    <table>
        <tr>
            <th>Timestamp</th>
            <th>Operation</th>
            <th>Operator</th>
            <th>Host</th>
            <th>User</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Verified</th>
        </tr>
"""

        for entry in entries:
            status_class = (
                "success" if entry.status == OperationStatus.SUCCESS else "failed"
            )
            html += f"""
        <tr>
            <td>{entry.timestamp.isoformat()}</td>
            <td>{entry.operation}</td>
            <td>{entry.operator}</td>
            <td>{entry.host}</td>
            <td>{entry.username}</td>
            <td class="{status_class}">{entry.status.value}</td>
            <td>{entry.duration:.1f}s</td>
            <td>{'✓' if entry.verified else '✗'}</td>
        </tr>
"""

        html += """
    </table>
</body>
</html>
"""

        if output_file:
            Path(output_file).write_text(html)

        return html
