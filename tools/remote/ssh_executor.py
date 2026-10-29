"""
SSH command execution on multiple remote hosts with parallel support and retry logic.
Migrates exec_ssh.sh to Python with enhanced features.
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from tools.core.logger import get_logger
from tools.core.exceptions import RemoteExecutionError

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of a single SSH execution."""

    host: str
    command: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    duration: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ExecutionStats:
    """Aggregated statistics for batch execution."""

    total_hosts: int = 0
    successful: int = 0
    failed: int = 0
    partial: int = 0
    total_duration: float = 0.0
    start_time: Optional[datetime] = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    results: List[ExecutionResult] = field(default_factory=list)

    def add_result(self, result: ExecutionResult) -> None:
        """Add result and update stats."""
        self.results.append(result)
        if result.success:
            self.successful += 1
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
            "duration_seconds": self.total_duration,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class SSHExecutor:
    """Execute commands on multiple SSH hosts with parallel support."""

    def __init__(
        self,
        user: str = "root",
        key_path: Optional[Path] = None,
        timeout: int = 10,
        max_retries: int = 1,
        strict_host_key_checking: bool = True,
    ):
        """Initialize SSH executor.

        Args:
            user: Remote user (default: root)
            key_path: Path to SSH private key (default: ~/.ssh/id_rsa)
            timeout: SSH connection timeout in seconds
            max_retries: Number of retries on failure
            strict_host_key_checking: Enable strict host key checking
        """
        self.user = user
        self.key_path = key_path or Path.home() / ".ssh" / "id_rsa"
        self.timeout = timeout
        self.max_retries = max_retries
        self.strict_host_key_checking = strict_host_key_checking
        self.stats = ExecutionStats()

    def _build_ssh_command(
        self, host: str, command: str, use_key: bool = True
    ) -> List[str]:
        """Build SSH command with proper arguments.

        Args:
            host: Remote host
            command: Command to execute
            use_key: Use private key authentication

        Returns:
            SSH command as list for subprocess
        """
        ssh_cmd = [
            "ssh",
            "-o",
            f"ConnectTimeout={self.timeout}",
            "-o",
            f"StrictHostKeyChecking={'yes' if self.strict_host_key_checking else 'no'}",
            "-o",
            "LogLevel=ERROR",
        ]

        if use_key and self.key_path.exists():
            ssh_cmd.extend(["-i", str(self.key_path)])

        ssh_cmd.append(f"{self.user}@{host}")
        ssh_cmd.append(command)

        return ssh_cmd

    def _execute_single(self, host: str, command: str) -> ExecutionResult:
        """Execute single command on host with retry logic.

        Args:
            host: Remote host
            command: Command to execute

        Returns:
            ExecutionResult with output and status
        """
        result = ExecutionResult(host=host, command=command, success=False)
        ssh_cmd = self._build_ssh_command(host, command)

        for attempt in range(self.max_retries + 1):
            try:
                start = time.time()
                process = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                duration = time.time() - start

                result.stdout = process.stdout
                result.stderr = process.stderr
                result.returncode = process.returncode
                result.duration = duration
                result.success = process.returncode == 0

                if result.success:
                    logger.debug(
                        f"[{host}] Command succeeded in {duration:.2f}s"
                    )
                    return result
                else:
                    logger.warning(
                        f"[{host}] Command failed with code {process.returncode}"
                    )
                    if attempt < self.max_retries:
                        logger.info(f"[{host}] Retrying (attempt {attempt + 2})...")
                        time.sleep(1)

            except subprocess.TimeoutExpired:
                result.error = f"SSH timeout after {self.timeout}s"
                logger.error(f"[{host}] {result.error}")
                if attempt < self.max_retries:
                    time.sleep(1)
            except Exception as e:
                result.error = str(e)
                logger.error(f"[{host}] Error: {e}")
                if attempt < self.max_retries:
                    time.sleep(1)

        return result

    def execute(
        self,
        hosts: List[str],
        command: str,
        parallel: int = 10,
    ) -> Tuple[List[ExecutionResult], ExecutionStats]:
        """Execute command on multiple hosts in parallel.

        Args:
            hosts: List of target hosts
            command: Command to execute
            parallel: Number of parallel workers

        Returns:
            Tuple of (results list, statistics)

        Raises:
            RemoteExecutionError: If all executions fail
        """
        self.stats = ExecutionStats(total_hosts=len(hosts))
        results = []

        logger.info(f"Executing on {len(hosts)} hosts with {parallel} workers")

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(self._execute_single, host, command): host
                for host in hosts
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                self.stats.add_result(result)
                logger.info(
                    f"[{result.host}] Completed ({self.stats.successful}/"
                    f"{len(hosts)} successful)"
                )

        self.stats.finalize()

        if self.stats.successful == 0:
            raise RemoteExecutionError(
                f"All {len(hosts)} executions failed"
            )

        logger.info(
            f"Execution completed: {self.stats.successful}/{len(hosts)}"
            f" successful in {self.stats.total_duration:.2f}s"
        )

        return results, self.stats

    def execute_script(
        self,
        hosts: List[str],
        script_path: Path,
        parallel: int = 10,
    ) -> Tuple[List[ExecutionResult], ExecutionStats]:
        """Execute a local script on remote hosts.

        Args:
            hosts: List of target hosts
            script_path: Path to local script
            parallel: Number of parallel workers

        Returns:
            Tuple of (results list, statistics)

        Raises:
            RemoteExecutionError: If script not found or all executions fail
        """
        try:
            with open(script_path, "r") as f:
                script_content = f.read()
        except OSError as exc:
            raise RemoteExecutionError(f"Script not found: {script_path}") from exc

        # Execute script via stdin to avoid file transfer
        command = f"bash -s << 'EOF'\n{script_content}\nEOF"
        return self.execute(hosts, command, parallel)
