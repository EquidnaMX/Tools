"""Tests for DNS replication checker."""

from unittest.mock import MagicMock, patch

import pytest

from tools.dns.replication_checker import (
    DNSReplicationChecker,
    ReplicationStatus,
    SerialComparison,
)


class TestSerialComparison:
    """SerialComparison dataclass tests."""

    def test_to_dict(self):
        comparison = SerialComparison(
            zone="example.com",
            master_serial="2026030701",
            slave_serial="2026030701",
            status=ReplicationStatus.OK,
        )

        data = comparison.to_dict()

        assert data["zone"] == "example.com"
        assert data["status"] == "ok"


class TestDNSReplicationChecker:
    """DNSReplicationChecker behavior tests."""

    @pytest.fixture
    def checker(self):
        return DNSReplicationChecker(
            master_ip="167.172.117.104",
            slave_ip="159.89.134.87",
            pdns_control_cmd="pdns_control",
            ssh_slave="root@159.89.134.87",
        )

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run, checker):
        mock_run.return_value = MagicMock(returncode=0, stdout="hello\n")

        out = checker._run_command(["echo", "hello"])

        assert out == "hello"

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run, checker):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        out = checker._run_command(["bad", "cmd"])

        assert out == ""

    @patch.object(DNSReplicationChecker, "_run_command")
    def test_get_zones_from_pdns(self, mock_cmd, checker):
        mock_cmd.return_value = "example.com.\ntest.org.\nexample.com.\n"

        zones = checker.get_zones_from_pdns()

        assert zones == ["example.com", "test.org"]

    @patch.object(DNSReplicationChecker, "soa_raw")
    def test_soa_serial_ok(self, mock_raw, checker):
        mock_raw.return_value = "ns1.example.com. hostmaster.example.com. 2026030701 3600 600 604800 3600"

        serial = checker.soa_serial("1.1.1.1", "example.com")

        assert serial == "2026030701"

    @patch.object(DNSReplicationChecker, "soa_raw")
    def test_soa_serial_invalid(self, mock_raw, checker):
        mock_raw.return_value = "invalid"

        serial = checker.soa_serial("1.1.1.1", "example.com")

        assert serial == ""

    @patch.object(DNSReplicationChecker, "_run_command")
    def test_validate_axfr_true(self, mock_cmd, checker):
        mock_cmd.return_value = "example.com. 3600 IN SOA ns1.example.com. hostmaster.example.com."

        assert checker.validate_axfr("1.1.1.1", "example.com") is True

    @patch.object(DNSReplicationChecker, "_run_command")
    def test_validate_axfr_false(self, mock_cmd, checker):
        mock_cmd.return_value = ""

        assert checker.validate_axfr("1.1.1.1", "example.com") is False

    @patch.object(DNSReplicationChecker, "soa_raw")
    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_compare_serials_ok(self, mock_serial, mock_raw, checker):
        mock_raw.side_effect = ["master raw", "slave raw"]
        mock_serial.side_effect = ["2026030701", "2026030701"]

        result = checker.compare_serials("example.com")

        assert result.status == ReplicationStatus.OK

    @patch.object(DNSReplicationChecker, "soa_raw")
    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_compare_serials_desync(self, mock_serial, mock_raw, checker):
        mock_raw.side_effect = ["master raw", "slave raw"]
        mock_serial.side_effect = ["2026030702", "2026030701"]

        result = checker.compare_serials("example.com")

        assert result.status == ReplicationStatus.DESYNC

    @patch.object(DNSReplicationChecker, "soa_raw")
    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_compare_serials_error_master(self, mock_serial, mock_raw, checker):
        mock_raw.side_effect = ["", "slave raw"]
        mock_serial.side_effect = ["", "2026030701"]

        result = checker.compare_serials("example.com")

        assert result.status == ReplicationStatus.ERROR_MASTER

    @patch.object(DNSReplicationChecker, "soa_raw")
    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_compare_serials_error_slave(self, mock_serial, mock_raw, checker):
        mock_raw.side_effect = ["master raw", ""]
        mock_serial.side_effect = ["2026030701", ""]

        result = checker.compare_serials("example.com")

        assert result.status == ReplicationStatus.ERROR_SLAVE

    @patch.object(DNSReplicationChecker, "_run_command")
    def test_trigger_retransfer_no_host(self, mock_cmd):
        checker = DNSReplicationChecker("1.1.1.1", "2.2.2.2", ssh_slave=None)

        assert checker.trigger_retransfer("example.com") is False
        mock_cmd.assert_not_called()

    @patch.object(DNSReplicationChecker, "_run_command")
    def test_trigger_retransfer_success(self, mock_cmd, checker):
        mock_cmd.return_value = "zone status"

        assert checker.trigger_retransfer("example.com") is True

    @patch.object(DNSReplicationChecker, "compare_serials")
    @patch.object(DNSReplicationChecker, "trigger_retransfer")
    def test_check_replication_with_retransfer(self, mock_retransfer, mock_compare, checker):
        first = SerialComparison(zone="example.com", status=ReplicationStatus.DESYNC)
        second = SerialComparison(
            zone="example.com",
            master_serial="2",
            slave_serial="2",
            status=ReplicationStatus.OK,
        )
        mock_compare.side_effect = [first, second]
        mock_retransfer.return_value = True

        results = checker.check_replication(zones=["example.com"])

        assert len(results) == 1
        assert results[0].status == ReplicationStatus.OK
        assert results[0].retransfer_attempted is True
        assert results[0].retransfer_success is True

    def test_get_summary(self):
        checker = DNSReplicationChecker("1.1.1.1", "2.2.2.2")
        results = [
            SerialComparison(zone="a", status=ReplicationStatus.OK),
            SerialComparison(zone="b", status=ReplicationStatus.DESYNC),
            SerialComparison(zone="c", status=ReplicationStatus.ERROR_MASTER),
            SerialComparison(zone="d", status=ReplicationStatus.ERROR_SLAVE),
        ]

        summary = checker.get_summary(results)

        assert summary["total_zones"] == 4
        assert summary["ok"] == 1
        assert summary["desync"] == 1
        assert summary["error_master"] == 1
        assert summary["error_slave"] == 1
