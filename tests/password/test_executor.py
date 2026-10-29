"""Tests for remote password executor."""

import asyncio
from unittest.mock import AsyncMock, patch

from tools.password.executor import RemotePasswordExecutor, SSHExecutor
from tools.password.models import OperationStatus


class DummyProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, *_args, **_kwargs):
        return self._stdout, self._stderr


def test_change_password_remote_success_path():
    executor = RemotePasswordExecutor(timeout=5)

    with patch.object(executor, "_detect_method", new=AsyncMock(return_value="chpasswd")), \
         patch.object(executor, "_change_with_chpasswd", new=AsyncMock(return_value=(True, "ok", ""))), \
         patch.object(executor, "verify_password_change", new=AsyncMock(return_value=True)):
        result = asyncio.run(
            executor.change_password_remote(
                host="server1",
                username="root",
                old_password="old",
                new_password="new",
            )
        )

    assert result.status == OperationStatus.SUCCESS
    assert result.verified is True
    assert result.method == "chpasswd"


def test_change_password_remote_failed_operation():
    executor = RemotePasswordExecutor(timeout=5)

    with patch.object(executor, "_detect_method", new=AsyncMock(return_value="passwd")), \
         patch.object(executor, "_change_with_passwd", new=AsyncMock(return_value=(False, "", "boom"))):
        result = asyncio.run(
            executor.change_password_remote(
                host="server1",
                username="root",
                old_password="old",
                new_password="new",
            )
        )

    assert result.status == OperationStatus.FAILED
    assert "boom" in (result.error or "")


def test_verify_password_change_returns_false_on_exception():
    executor = RemotePasswordExecutor(timeout=5)

    with patch("asyncio.create_subprocess_shell", side_effect=RuntimeError("ssh unavailable")):
        verified = asyncio.run(executor.verify_password_change("host", "user", "pw"))

    assert verified is False


def test_ssh_executor_builds_and_executes_command():
    process = DummyProcess(returncode=0, stdout=b"done", stderr=b"")

    with patch("asyncio.create_subprocess_shell", new=AsyncMock(return_value=process)) as mocked:
        returncode, stdout, stderr = asyncio.run(
            SSHExecutor.execute(host="host1", command="echo hi", username="root", timeout=5)
        )

    assert returncode == 0
    assert stdout == "done"
    assert stderr == ""
    command = mocked.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in command
    assert "StrictHostKeyChecking=no" not in command


def test_password_verification_requires_trusted_host():
    process = DummyProcess(returncode=0)
    with patch("asyncio.create_subprocess_shell", new=AsyncMock(return_value=process)) as mocked:
        assert asyncio.run(RemotePasswordExecutor().verify_password_change("example.test", "user", "dummy"))
    command = mocked.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in command
    assert "StrictHostKeyChecking=no" not in command
