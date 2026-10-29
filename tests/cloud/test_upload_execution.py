"""Upload executes the worker pool locally; the cloud boundary is simulated."""

from unittest.mock import Mock

import pytest

from tools.cloud.sync import DigitalOceanSync


@pytest.mark.parametrize("dry_run", [False, True])
def test_upload_processes_all_files_without_network(tmp_path, monkeypatch, dry_run):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_bytes(b"one")
    (source / "nested").mkdir()
    (source / "nested" / "b.bin").write_bytes(b"two")
    sync = DigitalOceanSync(
        region="sfo3",
        bucket="test-bucket",
        dest=str(tmp_path / "dest"),
        workers=2,
        dry_run=dry_run,
        show_progress=False,
        logger=Mock(),
    )
    sync.client = Mock()
    monkeypatch.setattr(sync, "_list_objects", lambda: iter([]))

    stats = sync.upload(str(source), dest_prefix="review")

    assert {item["key"] for item in stats.uploaded} == {
        "review/a.txt",
        "review/nested/b.bin",
    }
    assert stats.errors == []
    if dry_run:
        sync.client.upload_file.assert_not_called()
    else:
        calls = sync.client.upload_file.call_args_list
        assert {call.args[2] for call in calls} == {
            "review/a.txt",
            "review/nested/b.bin",
        }
        assert all(call.args[1] == "test-bucket" for call in calls)


def test_upload_worker_failure_is_reported(tmp_path, monkeypatch):
    source = tmp_path / "file.txt"
    source.write_bytes(b"data")
    sync = DigitalOceanSync(
        region="sfo3",
        bucket="test-bucket",
        dest=str(tmp_path / "dest"),
        workers=1,
        show_progress=False,
        logger=Mock(),
    )
    sync.client = Mock()
    sync.client.upload_file.side_effect = RuntimeError("simulated upload failure")
    monkeypatch.setattr(sync, "_list_objects", lambda: iter([]))
    monkeypatch.setattr("tools.cloud.sync.time.sleep", lambda _: None)

    stats = sync.upload(str(source))

    assert stats.uploaded == []
    assert len(stats.errors) == 1
    assert "simulated upload failure" in stats.errors[0]["error"]
    assert sync.client.upload_file.call_count == 3
