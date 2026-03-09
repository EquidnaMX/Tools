"""
File distribution to multiple remote hosts with compression and exclusion support.
Migrates update_hosts.sh to Python with enhanced features.
"""

import tarfile
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import fnmatch
import subprocess

from tools.core.logger import get_logger
from tools.core.exceptions import DistributionError

logger = get_logger(__name__)


@dataclass
class TransferResult:
    """Result of a single file transfer."""

    host: str
    local_path: str
    remote_path: str
    success: bool
    size_bytes: int = 0
    duration: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class DistributionResult:
    """Aggregated results for batch distribution."""

    total_hosts: int = 0
    successful: int = 0
    failed: int = 0
    total_bytes_transferred: int = 0
    total_duration: float = 0.0
    start_time: Optional[datetime] = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    results: List[TransferResult] = field(default_factory=list)

    def add_result(self, result: TransferResult) -> None:
        """Add transfer result and update stats."""
        self.results.append(result)
        if result.success:
            self.successful += 1
            self.total_bytes_transferred += result.size_bytes
        else:
            self.failed += 1

    def finalize(self) -> None:
        """Finalize statistics calculation."""
        self.end_time = datetime.now()
        if self.start_time:
            self.total_duration = (
                self.end_time - self.start_time
            ).total_seconds()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_hosts": self.total_hosts,
            "successful": self.successful,
            "failed": self.failed,
            "total_bytes": self.total_bytes_transferred,
            "duration_seconds": self.total_duration,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class FileDistributor:
    """Distribute files to multiple hosts via SCP with compression and filtering."""

    def __init__(
        self,
        user: str = "root",
        key_path: Optional[Path] = None,
        timeout: int = 30,
        exclude_patterns: Optional[List[str]] = None,
        dry_run: bool = False,
    ):
        """Initialize file distributor.

        Args:
            user: Remote user (default: root)
            key_path: Path to SSH private key
            timeout: SCP timeout in seconds
            exclude_patterns: Glob patterns to exclude
            dry_run: Show what would be done without doing it
        """
        self.user = user
        self.key_path = key_path
        self.timeout = timeout
        self.exclude_patterns = exclude_patterns or []
        self.dry_run = dry_run
        self.result = DistributionResult()

    def _should_exclude(self, path: Path) -> bool:
        """Check if path matches any exclude pattern.

        Args:
            path: Path to check

        Returns:
            True if should exclude
        """
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(str(path), pattern):
                return True
        return False

    def _create_archive(
        self, source_path: Path, compress: bool = True
    ) -> Path:
        """Create tar archive from source.

        Args:
            source_path: Directory or file to archive
            compress: Use gzip compression

        Returns:
            Path to created archive
        """
        fd, archive_name = tempfile.mkstemp(
            suffix=".tar.gz" if compress else ".tar"
        )
        temp_archive = Path(archive_name)
        # Close file descriptor returned by mkstemp; tarfile will reopen by path.
        os.close(fd)

        mode = "w:gz" if compress else "w"
        with tarfile.open(temp_archive, mode) as tar:
            if source_path.is_dir():
                for item in source_path.rglob("*"):
                    if not self._should_exclude(item):
                        arcname = item.relative_to(source_path.parent)
                        tar.add(item, arcname=arcname)
            else:
                tar.add(source_path, arcname=source_path.name)

        try:
            size_mb = temp_archive.stat().st_size / 1024 / 1024
            logger.info(f"Archive created: {temp_archive.name} ({size_mb:.2f} MB)")
        except OSError:
            logger.info(f"Archive created: {temp_archive.name}")
        return temp_archive

    def _build_scp_command(
        self, local_path: Path, host: str, remote_path: str
    ) -> List[str]:
        """Build SCP command with proper arguments.

        Args:
            local_path: Local file/directory
            host: Remote host
            remote_path: Remote destination path

        Returns:
            SCP command as list for subprocess
        """
        scp_cmd = [
            "scp",
            "-o",
            f"ConnectTimeout={self.timeout}",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "LogLevel=ERROR",
        ]

        if self.key_path is not None:
            scp_cmd.extend(["-i", str(self.key_path)])

        scp_cmd.extend([
            "-r",  # Recursive
            str(local_path),
            f"{self.user}@{host}:{remote_path}",
        ])

        return scp_cmd

    def _transfer_single(
        self, host: str, local_path: Path, remote_path: str
    ) -> TransferResult:
        """Transfer file to single host.

        Args:
            host: Remote host
            local_path: Local file to transfer
            remote_path: Remote destination

        Returns:
            TransferResult with outcome
        """
        result = TransferResult(
            host=host,
            local_path=str(local_path),
            remote_path=remote_path,
            success=False,
        )

        if not local_path.exists():
            result.error = f"Local path not found: {local_path}"
            logger.error(f"[{host}] {result.error}")
            return result

        if self.dry_run:
            logger.info(f"[{host}] DRY RUN: Would upload {local_path}")
            result.success = True
            result.size_bytes = (
                local_path.stat().st_size
                if local_path.is_file()
                else sum(
                    f.stat().st_size
                    for f in local_path.rglob("*")
                    if f.is_file()
                )
            )
            return result

        try:
            scp_cmd = self._build_scp_command(local_path, host, remote_path)
            logger.debug(f"[{host}] Executing: {' '.join(scp_cmd)}")

            process = subprocess.run(
                scp_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            if process.returncode == 0:
                result.success = True
                result.size_bytes = (
                    local_path.stat().st_size
                    if local_path.is_file()
                    else sum(
                        f.stat().st_size
                        for f in local_path.rglob("*")
                        if f.is_file()
                    )
                )
                logger.info(f"[{host}] Transfer successful")
            else:
                result.error = process.stderr or "SCP failed"
                logger.error(f"[{host}] {result.error}")

        except subprocess.TimeoutExpired:
            result.error = f"Transfer timeout after {self.timeout}s"
            logger.error(f"[{host}] {result.error}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"[{host}] Error: {e}")

        return result

    def upload_file(
        self,
        hosts: List[str],
        local_path: Path,
        remote_path: str,
        parallel: int = 5,
    ) -> Tuple[List[TransferResult], DistributionResult]:
        """Upload file to multiple hosts.

        Args:
            hosts: List of target hosts
            local_path: Local file to upload
            remote_path: Remote destination path
            parallel: Number of parallel transfers

        Returns:
            Tuple of (results list, statistics)

        Raises:
            DistributionError: If file not found
        """
        if not local_path.exists():
            raise DistributionError(f"File not found: {local_path}")

        self.result = DistributionResult(total_hosts=len(hosts))
        results = []

        logger.info(
            f"Uploading {local_path} to {len(hosts)} hosts"
            f" with {parallel} workers"
        )

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(
                    self._transfer_single, host, local_path, remote_path
                ): host
                for host in hosts
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                self.result.add_result(result)

        self.result.finalize()
        logger.info(
            f"Upload completed: {self.result.successful}/{len(hosts)}"
            f" successful in {self.result.total_duration:.2f}s"
        )

        return results, self.result

    def upload_directory(
        self,
        hosts: List[str],
        local_dir: Path,
        remote_path: str,
        compress: bool = False,
        parallel: int = 5,
    ) -> Tuple[List[TransferResult], DistributionResult]:
        """Upload directory to multiple hosts.

        Args:
            hosts: List of target hosts
            local_dir: Local directory to upload
            remote_path: Remote destination path
            compress: Create tar.gz archive first
            parallel: Number of parallel transfers

        Returns:
            Tuple of (results list, statistics)

        Raises:
            DistributionError: If directory not found
        """
        if not local_dir.exists() or not local_dir.is_dir():
            raise DistributionError(f"Directory not found: {local_dir}")

        if compress:
            archive_path = self._create_archive(local_dir, compress=True)
            try:
                return self.upload_file(
                    hosts, archive_path, remote_path + ".tar.gz", parallel
                )
            finally:
                archive_path.unlink()
        else:
            return self.upload_file(hosts, local_dir, remote_path, parallel)
