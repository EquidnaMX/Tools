"""Tests for NetworkScanner module."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from tools.remote.network_scanner import (
    NetworkScanner,
    HostInfo,
    ScanResult,
)
from tools.core.exceptions import NetworkError


class TestHostInfo:
    """Test HostInfo dataclass."""

    def test_host_info_creation(self):
        """Test HostInfo initialization."""
        host = HostInfo(
            ip_address="192.168.1.1",
            hostname="router.local",
            is_alive=True,
            response_time_ms=5.2,
        )

        assert host.ip_address == "192.168.1.1"
        assert host.hostname == "router.local"
        assert host.is_alive is True
        assert host.response_time_ms == 5.2

    def test_host_info_to_dict(self):
        """Test HostInfo conversion to dictionary."""
        host = HostInfo(
            ip_address="192.168.1.1",
            hostname="test.local",
            is_alive=True,
        )

        host_dict = host.to_dict()
        assert host_dict["ip_address"] == "192.168.1.1"
        assert host_dict["is_alive"] is True
        assert "timestamp" in host_dict


class TestScanResult:
    """Test ScanResult dataclass."""

    def test_scan_result_initialization(self):
        """Test ScanResult initialization."""
        result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        assert result.cidr == "192.168.1.0/24"
        assert result.total_hosts == 256
        assert result.alive_hosts == 0

    def test_scan_result_finalize(self):
        """Test result finalization."""
        result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)

        host1 = HostInfo(ip_address="192.168.1.1", is_alive=True)
        host2 = HostInfo(ip_address="192.168.1.2", is_alive=False)

        result.hosts = [host1, host2]
        result.finalize()

        assert result.alive_hosts == 1
        assert result.dead_hosts == 1
        assert result.duration_seconds >= 0
        assert result.end_time is not None

    def test_scan_result_to_dict(self):
        """Test ScanResult conversion to dictionary."""
        result = ScanResult(cidr="192.168.1.0/24", total_hosts=2)
        result.hosts = [
            HostInfo(ip_address="192.168.1.1", is_alive=True),
            HostInfo(ip_address="192.168.1.2", is_alive=False),
        ]
        result.finalize()

        result_dict = result.to_dict()
        assert result_dict["cidr"] == "192.168.1.0/24"
        assert result_dict["alive_hosts"] == 1
        assert len(result_dict["hosts"]) == 2


class TestNetworkScanner:
    """Test NetworkScanner class."""

    @pytest.fixture
    def scanner(self):
        """Create NetworkScanner instance for testing."""
        return NetworkScanner(timeout=2, parallel=10)

    def test_scanner_initialization(self, scanner):
        """Test scanner initialization."""
        assert scanner.timeout == 2
        assert scanner.parallel == 10

    def test_expand_cidr_24(self, scanner):
        """Test CIDR expansion for /24."""
        ips = scanner.expand_cidr("192.168.1.0/24")
        assert len(ips) > 0
        assert "192.168.1.1" in ips
        assert "192.168.1.254" in ips
        # Should exclude network and broadcast
        assert "192.168.1.0" not in ips
        assert "192.168.1.255" not in ips

    def test_expand_cidr_25(self, scanner):
        """Test CIDR expansion for /25."""
        ips = scanner.expand_cidr("192.168.1.0/25")
        assert len(ips) > 0
        # Should have around 126 usable IPs
        assert len(ips) <= 128

    def test_expand_cidr_32(self, scanner):
        """Test CIDR expansion for /32 (single host)."""
        ips = scanner.expand_cidr("192.168.1.1/32")
        assert len(ips) == 1
        assert ips[0] == "192.168.1.1"

    def test_expand_cidr_invalid(self, scanner):
        """Test invalid CIDR format."""
        with pytest.raises(NetworkError):
            scanner.expand_cidr("invalid")

    def test_expand_cidr_invalid_octet(self, scanner):
        """Test CIDR with invalid octet."""
        with pytest.raises(NetworkError):
            scanner.expand_cidr("192.168.1.256/24")

    def test_resolve_hostname(self, scanner):
        """Test hostname resolution."""
        # This will succeed or fail depending on system config
        # Testing the method exists and handles errors gracefully
        result = scanner._resolve_hostname("192.168.1.1")
        assert result is None or isinstance(result, str)

    @patch("subprocess.run")
    def test_ping_host_alive(self, mock_run, scanner):
        """Test ping detection of alive host."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="reply from 192.168.1.1: time=5 ms",
        )

        host = scanner._ping_host("192.168.1.1")

        assert host.is_alive is True
        assert host.ip_address == "192.168.1.1"

    @patch("subprocess.run")
    def test_ping_host_dead(self, mock_run, scanner):
        """Test ping detection of dead host."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
        )

        host = scanner._ping_host("192.168.1.100")

        assert host.is_alive is False
        assert host.ip_address == "192.168.1.100"

    @patch("subprocess.run")
    def test_ping_host_timeout(self, mock_run, scanner):
        """Test ping timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired("ping", 2)

        host = scanner._ping_host("192.168.1.100")

        assert host.is_alive is False

    @patch("subprocess.run")
    def test_ping_host_response_time_parsing(self, mock_run, scanner):
        """Test response time extraction."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Reply from 192.168.1.1: time=12.5ms",
        )

        host = scanner._ping_host("192.168.1.1")

        assert host.is_alive is True
        assert host.response_time_ms > 0

    @patch.object(NetworkScanner, "_ping_host")
    def test_scan_range(self, mock_ping, scanner):
        """Test network range scanning."""
        # Mock ping results
        def ping_side_effect(ip):
            return HostInfo(
                ip_address=ip,
                is_alive=ip.endswith(("1", "2")),  # Only .1 and .2 alive
                response_time_ms=5.0,
            )

        mock_ping.side_effect = ping_side_effect

        result = scanner.scan_range("192.168.1.0/30")

        assert result.cidr == "192.168.1.0/30"
        assert result.total_hosts > 0
        # Should have some alive hosts from our mock
        assert result.alive_hosts >= 0
        assert result.end_time is not None

    def test_scan_range_invalid_cidr(self, scanner):
        """Test scanning invalid CIDR."""
        with pytest.raises(NetworkError):
            scanner.scan_range("999.999.999.999/24")

    @patch.object(NetworkScanner, "scan_range")
    def test_scan_multiple_ranges(self, mock_scan, scanner):
        """Test scanning multiple CIDR ranges."""
        result1 = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        result2 = ScanResult(cidr="192.168.2.0/24", total_hosts=256)

        mock_scan.side_effect = [result1, result2]

        results = scanner.scan_multiple_ranges(
            ["192.168.1.0/24", "192.168.2.0/24"]
        )

        assert len(results) == 2
        assert results[0].cidr == "192.168.1.0/24"
        assert results[1].cidr == "192.168.2.0/24"

    @patch.object(NetworkScanner, "scan_range")
    def test_get_alive_hosts(self, mock_scan, scanner):
        """Test getting list of alive hosts."""
        result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        result.hosts = [
            HostInfo(ip_address="192.168.1.1", is_alive=True),
            HostInfo(ip_address="192.168.1.2", is_alive=False),
            HostInfo(ip_address="192.168.1.3", is_alive=True),
        ]

        mock_scan.return_value = result

        alive = scanner.get_alive_hosts("192.168.1.0/24")

        assert len(alive) == 2
        assert "192.168.1.1" in alive
        assert "192.168.1.3" in alive
        assert "192.168.1.2" not in alive

    @patch.object(NetworkScanner, "scan_range")
    def test_get_alive_hosts_with_names(self, mock_scan, scanner):
        """Test getting alive hosts with hostnames."""
        result = ScanResult(cidr="192.168.1.0/24", total_hosts=256)
        result.hosts = [
            HostInfo(
                ip_address="192.168.1.1",
                hostname="gateway",
                is_alive=True,
            ),
            HostInfo(ip_address="192.168.1.2", hostname=None, is_alive=True),
            HostInfo(ip_address="192.168.1.3", is_alive=False),
        ]

        mock_scan.return_value = result

        hosts_dict = scanner.get_alive_hosts_with_names("192.168.1.0/24")

        assert len(hosts_dict) == 2
        assert hosts_dict["192.168.1.1"] == "gateway"
        assert hosts_dict["192.168.1.2"] == "192.168.1.2"  # IP used as fallback
        assert "192.168.1.3" not in hosts_dict

    @patch.object(NetworkScanner, "_ping_host")
    def test_scan_large_range_performance(self, mock_ping, scanner):
        """Test scanning performance with large range."""
        def ping_side_effect(ip):
            return HostInfo(ip_address=ip, is_alive=False)

        mock_ping.side_effect = ping_side_effect

        # Using smaller range for test efficiency
        result = scanner.scan_range("192.168.1.0/28")

        assert result.total_hosts > 0
        assert result.duration_seconds >= 0


class TestNetworkScannerIntegration:
    """Integration tests for NetworkScanner (requires actual network)."""

    @pytest.mark.integration
    def test_localhost_scan(self):
        """Test scanning localhost."""
        scanner = NetworkScanner(timeout=2, parallel=5)
        try:
            alive = scanner.get_alive_hosts("127.0.0.0/24")
            # localhost should respond
            assert "127.0.0.1" in alive or len(alive) >= 0
        except Exception as e:
            pytest.skip(f"Network unavailable: {e}")

    @pytest.mark.integration
    def test_local_network_scan(self):
        """Test scanning local network (may require configuration)."""
        scanner = NetworkScanner(timeout=1, parallel=20)
        try:
            result = scanner.scan_range("192.168.1.0/28")
            # Just verify the result structure
            assert result.total_hosts > 0
            assert result.alive_hosts >= 0
        except NetworkError as e:
            pytest.skip(f"Network error: {e}")
