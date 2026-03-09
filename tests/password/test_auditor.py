"""Tests for password audit logger."""

from datetime import datetime, timedelta

from tools.password.auditor import AuditLogger
from tools.password.models import AuditEntry, OperationStatus


def test_log_and_query_entries(tmp_path):
    db_file = tmp_path / "audit.db"
    logger = AuditLogger(db_path=str(db_file))

    entry = AuditEntry(
        operation="change_success",
        operator="tester",
        host="server1",
        username="root",
        status=OperationStatus.SUCCESS,
        duration=1.2,
        verified=True,
        method="chpasswd",
    )
    logger.log_change(entry)

    entries = logger.query_log(host="server1", username="root")

    assert len(entries) == 1
    assert entries[0].operator == "tester"
    assert entries[0].status == OperationStatus.SUCCESS


def test_statistics_include_totals(tmp_path):
    db_file = tmp_path / "audit.db"
    logger = AuditLogger(db_path=str(db_file))

    logger.log_change(
        AuditEntry(
            operation="change_success",
            operator="alice",
            host="h1",
            username="root",
            status=OperationStatus.SUCCESS,
        )
    )
    logger.log_change(
        AuditEntry(
            operation="change_failed",
            operator="bob",
            host="h2",
            username="admin",
            status=OperationStatus.FAILED,
        )
    )

    stats = logger.get_statistics(
        from_date=datetime.utcnow() - timedelta(days=1),
        to_date=datetime.utcnow() + timedelta(days=1),
    )

    assert stats["total_changes"] == 2
    assert stats["by_status"]["success"] == 1
    assert stats["by_status"]["failed"] == 1


def test_export_report_json_csv_html(tmp_path):
    db_file = tmp_path / "audit.db"
    logger = AuditLogger(db_path=str(db_file))
    logger.log_change(
        AuditEntry(
            operation="change_success",
            operator="tester",
            host="h1",
            username="root",
            status=OperationStatus.SUCCESS,
        )
    )

    json_report = logger.export_report(format="json")
    csv_report = logger.export_report(format="csv")
    html_report = logger.export_report(format="html")

    assert "change_success" in json_report
    assert "timestamp" in csv_report
    assert "<html>" in html_report.lower()
