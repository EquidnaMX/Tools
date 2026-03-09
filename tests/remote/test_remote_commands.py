"""Tests for Remote Management CLI subcommands."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import tempfile

from tools.cli.remote_commands import (
    remote,
)
from tools.remote.ssh_executor import ExecutionResult, ExecutionStats
from tools.remote.file_distributor import TransferResult, DistributionResult
from tools.remote.network_scanner import HostInfo, ScanResult


class TestRemoteCLI:
    """Test remote management CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    def test_remote_group_exists(self):
        """Test remote command group is registered."""
        assert remote is not None
        assert remote.name == "remote"

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_basic(self, mock_executor_class, runner):
        """Test basic exec command."""
        # Set up mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        result_obj = ExecutionResult(
            host="192.168.1.1",
            command="echo test",
            success=True,
            stdout="test",
            stderr="",
            returncode=0,
        )
        stats = ExecutionStats(total_hosts=1)
        stats.add_result(result_obj)
        stats.finalize()

        mock_executor.execute.return_value = ([result_obj], stats)

        # Run command
        result = runner.invoke(remote, [
            "exec",
            "echo test",
            "--hosts",
            "192.168.1.1",
            "--timeout",
            "10",
            "--parallel",
            "1",
        ])

        assert result.exit_code == 0

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_dry_run(self, mock_executor_class, runner):
        """Test exec command with dry-run."""
        result = runner.invoke(remote, [
            "exec",
            "uptime",
            "--hosts",
            "192.168.1.1",
            "--dry-run",
        ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_multiple_hosts(self, mock_executor_class, runner):
        """Test exec command with multiple hosts."""
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        stats = ExecutionStats(total_hosts=3)
        for i in range(1, 4):
            result_obj = ExecutionResult(
                host=f"192.168.1.{i}",
                command="test",
                success=True,
                returncode=0,
            )
            stats.add_result(result_obj)
        stats.finalize()

        mock_executor.execute.return_value = (
            [ExecutionResult(
                host=f"192.168.1.{i}",
                command="test",
                success=True,
                returncode=0,
            ) for i in range(1, 4)],
            stats,
        )

        result = runner.invoke(remote, [
            "exec",
            "test",
            "--hosts", "192.168.1.1",
            "--hosts", "192.168.1.2",
            "--hosts", "192.168.1.3",
        ])

        assert result.exit_code == 0

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_json_output(self, mock_executor_class, runner):
        """Test exec command with JSON output."""
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        result_obj = ExecutionResult(
            host="test",
            command="test",
            success=True,
            returncode=0,
        )
        stats = ExecutionStats(total_hosts=1)
        stats.add_result(result_obj)

        mock_executor.execute.return_value = ([result_obj], stats)

        result = runner.invoke(remote, [
            "exec",
            "test",
            "--hosts", "192.168.1.1",
            "--output", "json",
        ])

        assert result.exit_code == 0
        assert "true" in result.output.lower()  # JSON boolean

    @patch("tools.cli.remote_commands.FileDistributor")
    def test_upload_file_basic(self, mock_distributor_class, runner):
        """Test basic file upload."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = Path(f.name)
            f.write(b"test content")

        try:
            mock_distributor = MagicMock()
            mock_distributor_class.return_value = mock_distributor

            transfer_result = TransferResult(
                host="192.168.1.1",
                local_path=str(temp_path),
                remote_path="/opt/test.txt",
                success=True,
                size_bytes=1024,
            )
            dist_result = DistributionResult(total_hosts=1)
            dist_result.add_result(transfer_result)
            dist_result.finalize()

            mock_distributor.upload_file.return_value = (
                [transfer_result],
                dist_result,
            )

            result = runner.invoke(remote, [
                "upload",
                str(temp_path),
                "/opt/test.txt",
                "--hosts",
                "192.168.1.1",
            ])

            assert result.exit_code == 0

        finally:
            temp_path.unlink()

    @patch("tools.cli.remote_commands.FileDistributor")
    def test_upload_directory(self, mock_distributor_class, runner):
        """Test directory upload."""
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "file.txt").write_text("content")

        try:
            mock_distributor = MagicMock()
            mock_distributor_class.return_value = mock_distributor

            transfer_result = TransferResult(
                host="192.168.1.1",
                local_path=str(temp_dir),
                remote_path="/opt/data",
                success=True,
                size_bytes=2048,
            )
            dist_result = DistributionResult(total_hosts=1)
            dist_result.add_result(transfer_result)
            dist_result.finalize()

            mock_distributor.upload_directory.return_value = (
                [transfer_result],
                dist_result,
            )

            result = runner.invoke(remote, [
                "upload",
                str(temp_dir),
                "/opt/data",
                "--hosts",
                "192.168.1.1",
            ])

            assert result.exit_code == 0

        finally:
            import shutil
            shutil.rmtree(temp_dir)

    @patch("tools.cli.remote_commands.FileDistributor")
    def test_upload_with_compression(self, mock_distributor_class, runner):
        """Test upload with compression."""
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "file.txt").write_text("content")

        try:
            mock_distributor = MagicMock()
            mock_distributor_class.return_value = mock_distributor

            transfer_result = TransferResult(
                host="test",
                local_path=str(temp_dir),
                remote_path="/opt/data.tar.gz",
                success=True,
                size_bytes=1024,
            )
            dist_result = DistributionResult(total_hosts=1)
            dist_result.add_result(transfer_result)

            mock_distributor.upload_directory.return_value = (
                [transfer_result],
                dist_result,
            )

            result = runner.invoke(remote, [
                "upload",
                str(temp_dir),
                "/opt/data",
                "--hosts",
                "192.168.1.1",
                "--compress",
            ])

            assert result.exit_code == 0

        finally:
            import shutil
            shutil.rmtree(temp_dir)

    @patch("tools.cli.remote_commands.FileDistributor")
    def test_upload_dry_run(self, mock_distributor_class, runner):
        """Test upload with dry-run."""
        mock_distributor = MagicMock()
        mock_distributor_class.return_value = mock_distributor
        transfer_result = TransferResult(
            host="192.168.1.1",
            local_path="/tmp/test.txt",
            remote_path="/opt/test.txt",
            success=True,
            size_bytes=4,
        )
        dist_result = DistributionResult(total_hosts=1)
        dist_result.add_result(transfer_result)
        dist_result.finalize()
        mock_distributor.upload_file.return_value = ([transfer_result], dist_result)

        temp_file = Path(tempfile.NamedTemporaryFile(delete=False).name)
        temp_file.write_text("test")

        try:
            result = runner.invoke(remote, [
                "upload",
                str(temp_file),
                "/opt/test.txt",
                "--hosts",
                "192.168.1.1",
                "--dry-run",
            ])

            assert result.exit_code == 0

        finally:
            temp_file.unlink()

    @patch("tools.cli.remote_commands.NetworkScanner")
    def test_scan_command_basic(self, mock_scanner_class, runner):
        """Test basic scan command."""
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner

        scan_result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        scan_result.hosts = [
            HostInfo(
                ip_address="192.168.1.1",
                hostname="gateway",
                is_alive=True,
                response_time_ms=5.0,
            ),
            HostInfo(
                ip_address="192.168.1.2",
                is_alive=False,
            ),
        ]
        scan_result.finalize()

        mock_scanner.scan_range.return_value = scan_result

        result = runner.invoke(remote, [
            "scan",
            "192.168.1.0/24",
        ])

        assert result.exit_code == 0
        assert "gateway" in result.output or "192.168.1.1" in result.output

    @patch("tools.cli.remote_commands.NetworkScanner")
    def test_scan_command_json_output(self, mock_scanner_class, runner):
        """Test scan command with JSON output."""
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner

        scan_result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        scan_result.hosts = [
            HostInfo(ip_address="192.168.1.1", is_alive=True)
        ]
        scan_result.finalize()

        mock_scanner.scan_range.return_value = scan_result

        result = runner.invoke(remote, [
            "scan",
            "192.168.1.0/24",
            "--output", "json",
        ])

        assert result.exit_code == 0
        assert "192.168.1.0/24" in result.output

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_no_hosts_error(self, mock_executor_class, runner):
        """Test exec command without hosts."""
        result = runner.invoke(remote, [
            "exec",
            "test",
        ])

        assert result.exit_code != 0

    def test_upload_command_nonexistent_file(self, runner):
        """Test upload command with non-existent file."""
        result = runner.invoke(remote, [
            "upload",
            "/nonexistent/file.txt",
            "/opt/test.txt",
            "--hosts",
            "192.168.1.1",
        ])

        assert result.exit_code != 0

    def test_scan_command_invalid_cidr(self, runner):
        """Test scan command with invalid CIDR."""
        runner_inst = CliRunner()
        with patch("tools.cli.remote_commands.NetworkScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner_class.return_value = mock_scanner
            from tools.core.exceptions import NetworkError

            mock_scanner.scan_range.side_effect = NetworkError("Invalid CIDR")

            result = runner_inst.invoke(remote, [
                "scan",
                "invalid",
            ])

            assert result.exit_code != 0

    @patch("tools.cli.remote_commands.SSHExecutor")
    def test_exec_command_with_options(self, mock_executor_class, runner):
        """Test exec command with all options."""
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        result_obj = ExecutionResult(
            host="192.168.1.1",
            command="test",
            success=True,
            returncode=0,
        )
        stats = ExecutionStats(total_hosts=1)
        stats.add_result(result_obj)

        mock_executor.execute.return_value = ([result_obj], stats)

        result = runner.invoke(remote, [
            "exec",
            "test",
            "--hosts", "192.168.1.1",
            "--user", "admin",
            "--timeout", "30",
            "--retries", "3",
            "--parallel", "5",
            "--output", "text",
        ])

        assert result.exit_code == 0
