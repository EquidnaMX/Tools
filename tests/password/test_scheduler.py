"""Tests for password rotation scheduler."""

from datetime import datetime, timedelta

from tools.password.models import RotationPolicy, RotationScheduleEntry
from tools.password.scheduler import PasswordRotationScheduler


def test_add_and_get_due_rotations(tmp_path):
    db_file = tmp_path / "rotation.db"
    scheduler = PasswordRotationScheduler(db_path=str(db_file))

    due_entry = RotationScheduleEntry(
        username="root",
        host="server1",
        next_rotation=datetime.utcnow() - timedelta(minutes=5),
        days_until_next=-1,
    )
    scheduler.add_rotation_entry(due_entry)

    due = scheduler.get_due_rotations()

    assert len(due) == 1
    assert due[0].host == "server1"


def test_mark_rotation_completed_updates_history(tmp_path):
    db_file = tmp_path / "rotation.db"
    scheduler = PasswordRotationScheduler(db_path=str(db_file))

    entry = RotationScheduleEntry(
        username="admin",
        host="server2",
        next_rotation=datetime.utcnow(),
    )
    scheduler.add_rotation_entry(entry)

    ok = scheduler.mark_rotation_completed(entry.id, RotationPolicy(rotation_interval_days=30), success=True)

    assert ok is True
    stats = scheduler.get_rotation_statistics()
    assert stats["total_scheduled"] >= 1


def test_get_upcoming_rotations(tmp_path):
    db_file = tmp_path / "rotation.db"
    scheduler = PasswordRotationScheduler(db_path=str(db_file))

    upcoming_entry = RotationScheduleEntry(
        username="svc",
        host="server3",
        next_rotation=datetime.utcnow() + timedelta(days=2),
        days_until_next=2,
    )
    scheduler.add_rotation_entry(upcoming_entry)

    upcoming = scheduler.get_upcoming_rotations(days_ahead=7)

    assert len(upcoming) == 1
    assert upcoming[0].username == "svc"
