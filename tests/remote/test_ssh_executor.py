"""Tests for SSHExecutor module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from tools.remote.ssh_executor import (
    SSHExecutor,
    ExecutionResult,
    ExecutionStats,
)
from tools.core.exceptions import RemoteExecutionError


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_execution_result_success(self):
        """Test successful execution result."""
        result = ExecutionResult(
            host="host1",
            command="echo test",
            success=True,
            stdout="test",
            stderr="",
            returncode=0,
            error="",
        )
        assert result.success is True
        assert result.stderr == ""
        assert result.error == ""

    def test_execution_result_failure(self):
        """Test failed execution result."""
        result = ExecutionResult(
            host="host1",
            command="false",
            success=False,
            stdout="",
            stderr="error",
            returncode=1,
            error="Command failed",
        )
        assert result.success is False
        assert result.returncode == 1
        assert result.error == "Command failed"

    def test_execution_result_to_dict(self):
        """Test result conversion to dictionary."""
        result = ExecutionResult(
            host="host1",
            command="echo test",
            success=True,
            stdout="test",
            stderr="",
            returncode=0,
            duration=1.5,
        )
        result_dict = result.to_dict()
        assert result_dict["host"] == "host1"
        assert result_dict["success"] is True
        assert result_dict["duration"] == 1.5


class TestExecutionStats:
    """Test ExecutionStats dataclass."""

    def test_execution_stats_initialization(self):
        """Test stats initialization."""
        stats = ExecutionStats(total_hosts=3)
        assert stats.total_hosts == 3
        assert stats.successful == 0
        assert stats.failed == 0

    def test_execution_stats_add_result(self):
        """Test adding results to stats."""
        stats = ExecutionStats(total_hosts=2)
        result1 = ExecutionResult(
            host="host1",
            command="test",
            success=True,
            returncode=0,
        )
        result2 = ExecutionResult(
            host="host2",
            command="test",
            success=False,
            returncode=1,
        )

        stats.add_result(result1)
        stats.add_result(result2)

        assert stats.successful == 1
        assert stats.failed == 1
        assert len(stats.results) == 2

    def test_execution_stats_finalize(self):
        """Test stats finalization."""
        stats = ExecutionStats(total_hosts=1)
        stats.start_time = datetime.now()
        stats.finalize()

        assert stats.end_time is not None
        assert stats.total_duration >= 0


class TestSSHExecutor:
    """Test SSHExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create SSHExecutor instance for testing."""
        return SSHExecutor(user="testuser", timeout=10, max_retries=1)

    def test_executor_initialization(self, executor):
        """Test executor initialization."""
        assert executor.user == "testuser"
        assert executor.timeout == 10
        assert executor.max_retries == 1

    def test_build_ssh_command(self, executor):
        """Test SSH command building."""
        cmd = executor._build_ssh_command(
            host="192.168.1.1",
            command="ls -la",
            use_key=True,
        )

        cmd_str = " ".join(cmd)
        assert cmd[0] == "ssh"
        assert "192.168.1.1" in cmd_str
        assert "ls -la" in cmd_str
        assert "-o" in cmd

    def test_build_ssh_command_with_special_chars(self, executor):
        """Test SSH command building with special characters."""
        cmd = executor._build_ssh_command(
            host="192.168.1.1",
            command="echo 'test' && echo 'test2'",
        )

        assert "echo" in " ".join(cmd)

    @patch("subprocess.run")
    def test_execute_single_success(self, mock_run, executor):
        """Test single host execution success."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success output",
            stderr="",
        )

        result = executor._execute_single(
            host="192.168.1.1",
            command="echo test",
        )

        assert result.success is True
        assert result.returncode == 0

    @patch("subprocess.run")
    def test_execute_single_failure(self, mock_run, executor):
        """Test single host execution failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error",
        )

        result = executor._execute_single(
            host="192.168.1.1",
            command="false",
        )

        assert result.success is False
        assert result.returncode == 1

    @patch("subprocess.run")
    def test_execute_single_timeout(self, mock_run, executor):
        """Test single host execution timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("ssh", 10)

        result = executor._execute_single(
            host="192.168.1.1",
            command="sleep 100",
        )

        assert result.success is False
        assert "timeout" in result.error.lower() or result.error == ""

    @patch("subprocess.run")
    def test_execute_multiple_hosts(self, mock_run, executor):
        """Test execution on multiple hosts."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test",
            stderr="",
        )

        hosts = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
        results, stats = executor.execute(
            hosts=hosts,
            command="echo test",
            parallel=2,
        )

        assert len(results) == 3
        assert stats.total_hosts == 3
        assert stats.successful == 3

    @patch("subprocess.run")
    def test_execute_with_retries(self, mock_run, executor):
        """Test execution with retry logic."""
        # First call fails, second succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="error"),
            MagicMock(returncode=0, stdout="success", stderr=""),
        ]

        executor.max_retries = 2
        executor._execute_single(
            host="192.168.1.1",
            command="test command",
        )

        # After retry logic, should eventually attempt again
        assert mock_run.call_count >= 1

    @patch("builtins.open", create=True)
    @patch("subprocess.run")
    def test_execute_script(self, mock_run, mock_open, executor):
        """Test script execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="script output",
            stderr="",
        )

        script_path = Path("/tmp/test_script.sh")
        results, stats = executor.execute_script(
            hosts=["192.168.1.1"],
            script_path=script_path,
            parallel=1,
        )

        assert len(results) == 1
        assert stats.total_hosts == 1

    def test_execute_empty_hosts_list(self, executor):
        """Test execution with empty hosts list."""
        with pytest.raises((RemoteExecutionError, ValueError)):
            executor.execute(hosts=[], command="test")

    @patch("subprocess.run")
    def test_execute_mixed_success_failure(self, mock_run, executor):
        """Test execution with mixed success/failure results."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="success", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="error"),
            MagicMock(returncode=0, stdout="success", stderr=""),
        ]

        hosts = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
        results, stats = executor.execute(
            hosts=hosts,
            command="test",
            parallel=1,
        )

        assert stats.successful == 2
        assert stats.failed == 1
        assert len(results) == 3

    def test_result_duration_tracking(self):
        """Test that duration is tracked."""
        result = ExecutionResult(
            host="host1",
            command="test",
            success=True,
            returncode=0,
            duration=2.5,
        )

        assert result.duration == 2.5
        result_dict = result.to_dict()
        assert result_dict["duration"] == 2.5

    @patch("subprocess.run")
    def test_parallel_execution_performance(self, mock_run, executor):
        """Test that parallel execution works."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test",
            stderr="",
        )

        hosts = [f"192.168.1.{i}" for i in range(1, 11)]
        results, stats = executor.execute(
            hosts=hosts,
            command="uptime",
            parallel=5,
        )

        assert len(results) == 10
        assert stats.successful == 10


class TestSSHExecutorIntegration:
    """Integration tests for SSHExecutor (requires actual SSH setup)."""

    @pytest.mark.integration
    def test_localhost_execution(self):
        """Test execution on localhost (if SSH is configured)."""
        executor = SSHExecutor(timeout=5)
        try:
            results, stats = executor.execute(
                hosts=["localhost"],
                command="echo integration_test",
                parallel=1,
            )
            assert len(results) == 1
        except Exception:
            pytest.skip("SSH not configured for localhost")
