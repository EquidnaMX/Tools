from pathlib import Path

import pytest

from tools.backup.manager import BackupError, BackupManager


def test_create_and_list_backup(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("hello")

    backup_dir = tmp_path / "backups"
    manager = BackupManager(backup_dir, keep=3)

    created = manager.create_backup(source_dir, name="daily")

    assert created.exists()
    listed = manager.list_backups(prefix="daily")
    assert len(listed) == 1
    assert listed[0].path == created


def test_rotation_keeps_newest(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("hello")

    backup_dir = tmp_path / "backups"
    manager = BackupManager(backup_dir, keep=2)

    manager.create_backup(source_dir, name="daily")
    manager.create_backup(source_dir, name="daily")
    manager.create_backup(source_dir, name="daily")

    deleted = manager.apply_rotation(prefix="daily", keep=1)

    assert len(deleted) == 2
    assert len(manager.list_backups(prefix="daily")) == 1


def test_restore_backup(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    original = source_dir / "hello.txt"
    original.write_text("backup-content")

    manager = BackupManager(tmp_path / "backups")
    backup_file = manager.create_backup(source_dir, name="restore")

    destination = tmp_path / "restore-target"
    restored_root = manager.restore_backup(backup_file, destination=destination)

    restored_file = restored_root / "hello.txt"
    assert restored_file.exists()
    assert restored_file.read_text() == "backup-content"


def test_create_backup_missing_source_raises(tmp_path: Path):
    manager = BackupManager(tmp_path / "backups")
    with pytest.raises(BackupError):
        manager.create_backup(tmp_path / "does-not-exist")
