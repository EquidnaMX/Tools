"""Tests for DNS zone manager."""

from unittest.mock import patch

import pytest

from tools.dns.replication_checker import DNSReplicationChecker
from tools.dns.zone_manager import DNSZoneManager


class TestDNSZoneManager:
    """DNSZoneManager behavior tests."""

    @pytest.fixture
    def manager(self):
        checker = DNSReplicationChecker(master_ip="1.1.1.1", slave_ip="2.2.2.2")
        return DNSZoneManager(checker)

    @patch.object(DNSReplicationChecker, "get_zones_from_pdns")
    def test_list_zones(self, mock_zones, manager):
        mock_zones.return_value = ["example.com", "test.org"]

        zones = manager.list_zones()

        assert zones == ["example.com", "test.org"]

    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_get_soa_info(self, mock_serial, manager):
        mock_serial.side_effect = ["2026030702", "2026030701"]

        info = manager.get_soa_info("example.com")

        assert info.zone == "example.com"
        assert info.master_serial == "2026030702"
        assert info.slave_serial == "2026030701"

    @patch.object(DNSReplicationChecker, "soa_serial")
    def test_get_soa_info_to_dict(self, mock_serial, manager):
        mock_serial.side_effect = ["1", "1"]

        info = manager.get_soa_info("example.com")
        data = info.to_dict()

        assert data["zone"] == "example.com"
        assert data["master_serial"] == "1"
        assert data["slave_serial"] == "1"
