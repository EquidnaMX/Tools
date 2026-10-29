"""Tests for FileDistributor module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

from tools.remote.file_distributor import (
    FileDistributor,
    TransferResult,
    DistributionResult,
)
from tools.core.exceptions import DistributionError


class TestTransferResult:
    """Test TransferResult dataclass."""

    def test_transfer_result_success(self):
        """Test successful transfer result."""
        result = TransferResult(
            host="host1",
            local_path="/tmp/file.txt",
            remote_path="/opt/file.txt",
            success=True,
            size_bytes=1024,
            duration=2.5,
        )

        assert result.success is True
        assert result.size_bytes == 1024
        assert result.duration == 2.5

    def test_transfer_result_to_dict(self):
        """Test result conversion to dictionary."""
        result = TransferResult(
            host="host1",
            local_path="/tmp/file.txt",
            remote_path="/opt/file.txt",
            success=True,
            size_bytes=512,
        )

        result_dict = result.to_dict()
        assert result_dict["host"] == "host1"
        assert result_dict["size_bytes"] == 512
        assert result_dict["success"] is True


class TestDistributionResult:
    """Test DistributionResult dataclass."""

    def test_distribution_result_initialization(self):
        """Test result initialization."""
        result = DistributionResult(total_hosts=5)
        assert result.total_hosts == 5
        assert result.successful == 0
        assert result.failed == 0
        assert result.total_bytes_transferred == 0

    def test_distribution_result_add_result(self):
        """Test adding transfer results."""
        dist_result = DistributionResult(total_hosts=2)

        transfer1 = TransferResult(
            host="host1",
            local_path="/tmp/f1",
            remote_path="/opt/f1",
            success=True,
            size_bytes=1024,
        )

        transfer2 = TransferResult(
            host="host2",
            local_path="/tmp/f2",
            remote_path="/opt/f2",
            success=False,
            size_bytes=0,
        )

        dist_result.add_result(transfer1)
        dist_result.add_result(transfer2)

        assert dist_result.successful == 1
        assert dist_result.failed == 1
        assert dist_result.total_bytes_transferred == 1024

    def test_distribution_result_finalize(self):
        """Test result finalization."""
        dist_result = DistributionResult()
        dist_result.finalize()

        assert dist_result.end_time is not None
        assert dist_result.total_duration >= 0


class TestFileDistributor:
    """Test FileDistributor class."""

    @pytest.fixture
    def distributor(self):
        """Create FileDistributor instance for testing."""
        return FileDistributor(user="testuser", timeout=10)

    @pytest.fixture
    def temp_file(self):
        """Create temporary file for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            suffix=".txt",
        ) as f:
            f.write("test content")
            path = Path(f.name)
        yield path
        path.unlink()

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory with files for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "file2.txt").write_text("content2")
        (temp_dir / "subdir").mkdir()
        (temp_dir / "subdir" / "file3.txt").write_text("content3")
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir)

    def test_distributor_initialization(self, distributor):
        """Test distributor initialization."""
        assert distributor.user == "testuser"
        assert distributor.timeout == 10
        assert distributor.dry_run is False

    def test_should_exclude_file(self, distributor):
        """Test file exclusion logic."""
        distributor.exclude_patterns = ["*.pyc", "__pycache__"]

        assert distributor._should_exclude(Path("test.pyc")) is True
        assert distributor._should_exclude(Path("test.py")) is False
        assert distributor._should_exclude(Path("__pycache__")) is True

    def test_should_exclude_no_patterns(self, distributor):
        """Test exclude when no patterns defined."""
        assert distributor._should_exclude(Path("anyfile.txt")) is False

    @patch("tempfile.NamedTemporaryFile")
    @patch("tarfile.open")
    def test_create_archive(self, mock_tar, mock_tempfile, distributor, temp_dir):
        """Test archive creation."""
        mock_tempfile.return_value = MagicMock(
            name="/tmp/archive.tar.gz"
        )
        mock_tar_instance = MagicMock()
        mock_tar.return_value.__enter__.return_value = mock_tar_instance

        archive_path = distributor._create_archive(temp_dir, compress=True)

        assert archive_path.suffix == ".gz" or ".tar" in str(archive_path)

    def test_build_scp_command_with_key(self):
        """Test SCP command building with SSH key."""
        key_path = Path.home() / ".ssh" / "id_rsa"
        distributor = FileDistributor(user="admin", key_path=key_path)

        cmd = distributor._build_scp_command(
            local_path=Path("/tmp/file.txt"),
            host="192.168.1.1",
            remote_path="/opt/file.txt",
        )

        cmd_str = " ".join(cmd)
        assert "scp" in cmd
        assert str(key_path) in cmd_str
        assert "file.txt" in cmd_str
        assert "admin@192.168.1.1:/opt/file.txt" in cmd_str

    def test_build_scp_command_without_key(self, distributor):
        """Test SCP command building without SSH key."""
        cmd = distributor._build_scp_command(
            local_path=Path("/tmp/file.txt"),
            host="192.168.1.1",
            remote_path="/opt/file.txt",
        )

        cmd_str = " ".join(cmd)
        assert "scp" in cmd
        assert "testuser@192.168.1.1:/opt/file.txt" in cmd_str
        assert "-i" not in cmd_str  # No SSH key should be included
        assert "StrictHostKeyChecking=yes" in cmd
        assert not any("UserKnownHostsFile=" in argument for argument in cmd)

    @patch("subprocess.run")
    def test_transfer_single_success(
        self,
        mock_run,
        distributor,
        temp_file,
    ):
        """Test single file transfer success."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = distributor._transfer_single(
            host="192.168.1.1",
            local_path=temp_file,
            remote_path="/opt/file.txt",
        )

        assert result.success is True
        assert result.host == "192.168.1.1"

    @patch("subprocess.run")
    def test_transfer_single_failure(
        self,
        mock_run,
        distributor,
        temp_file,
    ):
        """Test single file transfer failure."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")

        result = distributor._transfer_single(
            host="192.168.1.1",
            local_path=temp_file,
            remote_path="/opt/file.txt",
        )

        assert result.success is False
        assert "Permission denied" in result.error

    def test_transfer_single_nonexistent_file(self, distributor):
        """Test transfer of non-existent file."""
        result = distributor._transfer_single(
            host="192.168.1.1",
            local_path=Path("/nonexistent/file.txt"),
            remote_path="/opt/file.txt",
        )

        assert result.success is False
        assert "not found" in result.error

    def test_transfer_single_dry_run(self, distributor, temp_file):
        """Test dry-run mode."""
        distributor.dry_run = True

        result = distributor._transfer_single(
            host="192.168.1.1",
            local_path=temp_file,
            remote_path="/opt/file.txt",
        )

        assert result.success is True  # Dry run always succeeds
        assert result.size_bytes > 0

    @patch("subprocess.run")
    def test_upload_file(self, mock_run, distributor, temp_file):
        """Test file upload to multiple hosts."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        hosts = ["192.168.1.1", "192.168.1.2"]
        results, dist_result = distributor.upload_file(
            hosts=hosts,
            local_path=temp_file,
            remote_path="/opt/file.txt",
            parallel=2,
        )

        assert len(results) == 2
        assert dist_result.total_hosts == 2
        assert dist_result.successful >= 0

    def test_upload_file_nonexistent(self, distributor):
        """Test upload of non-existent file."""
        with pytest.raises(DistributionError):
            distributor.upload_file(
                hosts=["192.168.1.1"],
                local_path=Path("/nonexistent/file.txt"),
                remote_path="/opt/file.txt",
            )

    @patch("subprocess.run")
    def test_upload_directory(
        self,
        mock_run,
        distributor,
        temp_dir,
    ):
        """Test directory upload."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        results, dist_result = distributor.upload_directory(
            hosts=["192.168.1.1"],
            local_dir=temp_dir,
            remote_path="/opt/data",
            parallel=1,
        )

        assert len(results) >= 1
        assert dist_result.total_hosts == 1

    def test_upload_directory_nonexistent(self, distributor):
        """Test upload of non-existent directory."""
        with pytest.raises(DistributionError):
            distributor.upload_directory(
                hosts=["192.168.1.1"],
                local_dir=Path("/nonexistent/dir"),
                remote_path="/opt/data",
            )

    @patch("subprocess.run")
    def test_upload_directory_with_compression(
        self,
        mock_run,
        distributor,
        temp_dir,
    ):
        """Test directory upload with compression."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        results, dist_result = distributor.upload_directory(
            hosts=["192.168.1.1"],
            local_dir=temp_dir,
            remote_path="/opt/data.tar.gz",
            compress=True,
            parallel=1,
        )

        assert len(results) >= 1

    @patch("subprocess.run")
    def test_upload_with_exclude_patterns(
        self,
        mock_run,
        distributor,
        temp_dir,
    ):
        """Test upload with file exclusion patterns."""
        distributor.exclude_patterns = ["*.pyc", "__pycache__"]
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        results, dist_result = distributor.upload_directory(
            hosts=["192.168.1.1"],
            local_dir=temp_dir,
            remote_path="/opt/data",
            parallel=1,
        )

        assert len(results) >= 1

    @patch("subprocess.run")
    def test_distribution_with_mixed_results(
        self,
        mock_run,
        distributor,
        temp_file,
    ):
        """Test distribution with mixed success/failure."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),
            MagicMock(returncode=1, stderr="Connection refused"),
            MagicMock(returncode=0, stderr=""),
        ]

        hosts = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
        results, dist_result = distributor.upload_file(
            hosts=hosts,
            local_path=temp_file,
            remote_path="/opt/file.txt",
            parallel=1,
        )

        assert dist_result.successful == 2
        assert dist_result.failed == 1
        assert len(results) == 3
