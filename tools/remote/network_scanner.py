"""
Network host discovery and scanning functions.
Provides CIDR range expansion and ping-based host discovery.
"""

import ipaddress
import socket
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tools.core.logger import get_logger
from tools.core.exceptions import NetworkError

logger = get_logger(__name__)


@dataclass
class HostInfo:
    """Information about a discovered host."""

    ip_address: str
    hostname: Optional[str] = None
    is_alive: bool = False
    response_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["timestamp"] = data["timestamp"].isoformat()
        return data


@dataclass
class ScanResult:
    """Results of network scan."""

    cidr: str
    total_hosts: int = 0
    alive_hosts: int = 0
    dead_hosts: int = 0
    hosts: List[HostInfo] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0

    def finalize(self) -> None:
        """Calculate final statistics."""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.alive_hosts = sum(1 for h in self.hosts if h.is_alive)
        self.dead_hosts = len(self.hosts) - self.alive_hosts

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cidr": self.cidr,
            "total_hosts": self.total_hosts,
            "alive_hosts": self.alive_hosts,
            "dead_hosts": self.dead_hosts,
            "duration_seconds": self.duration_seconds,
            "hosts": [h.to_dict() for h in self.hosts],
        }


class NetworkScanner:
    """Discover and scan hosts in network CIDR ranges."""

    def __init__(self, timeout: int = 2, parallel: int = 20):
        """Initialize network scanner.

        Args:
            timeout: Ping timeout in seconds
            parallel: Number of parallel pings
        """
        self.timeout = timeout
        self.parallel = parallel

    def expand_cidr(self, cidr: str) -> List[str]:
        """Expand CIDR notation to individual IP addresses.

        Args:
            cidr: CIDR range (e.g., '192.168.1.0/24')

        Returns:
            List of IP addresses

        Raises:
            NetworkError: If CIDR is invalid
        """
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            # Exclude network and broadcast addresses
            hosts = list(network.hosts())
            if not hosts:  # /31 or /32 networks
                hosts = list(network)

            logger.debug(f"CIDR {cidr} expands to {len(hosts)} hosts")
            return [str(ip) for ip in hosts]

        except ValueError as e:
            raise NetworkError(f"Invalid CIDR notation: {cidr}") from e

    def _resolve_hostname(self, ip_address: str) -> Optional[str]:
        """Reverse DNS lookup for IP address.

        Args:
            ip_address: IP to resolve

        Returns:
            Hostname or None if lookup fails
        """
        try:
            hostname, _, _ = socket.gethostbyaddr(ip_address)
            return hostname
        except socket.herror:
            return None

    def _ping_host(self, ip_address: str) -> HostInfo:
        """Ping a single host.

        Args:
            ip_address: IP address to ping

        Returns:
            HostInfo with alive status and response time
        """
        host_info = HostInfo(ip_address=ip_address)

        # Platform-specific ping parameters
        ping_cmd = (
            ["ping", "-n", "1", "-w", str(self.timeout * 1000), ip_address]
            if subprocess.os.name == "nt"  # Windows
            else ["ping", "-c", "1", "-W", str(self.timeout * 1000), ip_address]
        )

        try:
            result = subprocess.run(
                ping_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 1,
                check=False,
            )

            if result.returncode == 0:
                host_info.is_alive = True
                # Extract response time (simple parsing)
                if "time=" in result.stdout:
                    try:
                        time_str = result.stdout.split("time=")[-1].split("ms")[0]
                        host_info.response_time_ms = float(time_str.strip())
                    except (ValueError, IndexError):
                        host_info.response_time_ms = 0.0

                # Try reverse DNS
                host_info.hostname = self._resolve_hostname(ip_address)
                logger.debug(f"[{ip_address}] ALIVE ({host_info.response_time_ms}ms)")

            else:
                logger.debug(f"[{ip_address}] DEAD")

        except subprocess.TimeoutExpired:
            logger.debug(f"[{ip_address}] TIMEOUT")
        except Exception as e:
            logger.warning(f"[{ip_address}] Error: {e}")

        return host_info

    def scan_range(self, cidr: str) -> ScanResult:
        """Scan CIDR range for alive hosts.

        Args:
            cidr: CIDR range to scan

        Returns:
            ScanResult with discovered hosts

        Raises:
            NetworkError: If CIDR is invalid
        """
        hosts_list = self.expand_cidr(cidr)
        result = ScanResult(cidr=cidr, total_hosts=len(hosts_list))

        logger.info(
            f"Scanning {cidr} ({len(hosts_list)} hosts)"
            f" with {self.parallel} workers"
        )

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            futures = {
                executor.submit(self._ping_host, ip): ip for ip in hosts_list
            }

            for i, future in enumerate(as_completed(futures), 1):
                host_info = future.result()
                result.hosts.append(host_info)

                if i % 50 == 0:
                    progress = (i / len(hosts_list)) * 100
                    logger.info(f"Progress: {progress:.1f}% ({i}/{len(hosts_list)})")

        result.finalize()
        logger.info(
            f"Scan complete: {result.alive_hosts} alive,"
            f" {result.dead_hosts} dead in {result.duration_seconds:.2f}s"
        )

        return result

    def scan_multiple_ranges(self, cidrs: List[str]) -> List[ScanResult]:
        """Scan multiple CIDR ranges sequentially.

        Args:
            cidrs: List of CIDR ranges

        Returns:
            List of ScanResult objects

        Raises:
            NetworkError: If any CIDR is invalid
        """
        results = []
        for cidr in cidrs:
            result = self.scan_range(cidr)
            results.append(result)

        return results

    def get_alive_hosts(self, cidr: str) -> List[str]:
        """Scan range and return list of alive host IPs.

        Args:
            cidr: CIDR range to scan

        Returns:
            List of IP addresses that responded to ping

        Raises:
            NetworkError: If CIDR is invalid
        """
        result = self.scan_range(cidr)
        return [host.ip_address for host in result.hosts if host.is_alive]

    def get_alive_hosts_with_names(self, cidr: str) -> dict:
        """Scan range and return alive hosts with hostnames.

        Args:
            cidr: CIDR range to scan

        Returns:
            Dictionary of {ip: hostname} for alive hosts

        Raises:
            NetworkError: If CIDR is invalid
        """
        result = self.scan_range(cidr)
        return {
            host.ip_address: (host.hostname or host.ip_address)
            for host in result.hosts
            if host.is_alive
        }
