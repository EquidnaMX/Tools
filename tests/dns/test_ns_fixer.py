"""Tests for DNS NS fixer."""

from unittest.mock import patch

import pytest

from tools.dns.ns_fixer import DNSNSFixer, NSFixMode


class TestDNSNSFixer:
    """DNSNSFixer behavior tests."""

    @pytest.fixture
    def fixer(self):
        return DNSNSFixer(
            ns1="ns1.example.com",
            ns2="ns2.example.com.",
            ttl=3600,
            mode=NSFixMode.ENFORCE,
            pdnsutil_cmd="pdnsutil",
            pdns_control_cmd="pdns_control",
        )

    def test_normalize_fqdn(self, fixer):
        assert fixer._normalize_fqdn("ns1.example.com") == "ns1.example.com."
        assert fixer._normalize_fqdn("ns2.example.com.") == "ns2.example.com."

    def test_desired_ns(self, fixer):
        assert fixer._desired_ns() == ["ns1.example.com.", "ns2.example.com."]

    @patch.object(DNSNSFixer, "_run_command")
    def test_list_zones(self, mock_cmd, fixer):
        mock_cmd.return_value = "example.com\ntest.org\n"

        zones = fixer.list_zones()

        assert zones == ["example.com", "test.org"]

    @patch.object(DNSNSFixer, "_run_command")
    def test_get_zone_ns(self, mock_cmd, fixer):
        mock_cmd.return_value = "@ NS ns1.example.com\n@ NS ns2.example.com.\n@ A 1.1.1.1"

        ns_records = fixer.get_zone_ns("example.com")

        assert ns_records == ["ns1.example.com.", "ns2.example.com."]

    @patch.object(DNSNSFixer, "_run_command")
    @patch.object(DNSNSFixer, "get_zone_ns")
    def test_fix_zone_enforce_unchanged(self, mock_get_ns, mock_cmd, fixer):
        mock_get_ns.return_value = ["ns1.example.com.", "ns2.example.com."]

        result = fixer.fix_zone("example.com")

        assert result.status == "unchanged"
        assert result.changed is False
        mock_cmd.assert_not_called()

    @patch.object(DNSNSFixer, "_enforce_zone")
    @patch.object(DNSNSFixer, "get_zone_ns")
    def test_fix_zone_enforce_changed(self, mock_get_ns, mock_enforce, fixer):
        mock_get_ns.return_value = ["old-ns.example.com."]
        mock_enforce.return_value = True

        result = fixer.fix_zone("example.com")

        assert result.status == "changed"
        assert result.changed is True

    @patch.object(DNSNSFixer, "_enforce_zone")
    @patch.object(DNSNSFixer, "get_zone_ns")
    def test_fix_zone_enforce_failed(self, mock_get_ns, mock_enforce, fixer):
        mock_get_ns.return_value = ["old-ns.example.com."]
        mock_enforce.return_value = False

        result = fixer.fix_zone("example.com")

        assert result.status == "failed"
        assert result.changed is False

    @patch.object(DNSNSFixer, "_append_zone")
    @patch.object(DNSNSFixer, "get_zone_ns")
    def test_fix_zone_append_changed(self, mock_get_ns, mock_append):
        fixer = DNSNSFixer(
            ns1="ns1.example.com",
            ns2="ns2.example.com",
            mode=NSFixMode.APPEND,
        )
        mock_get_ns.return_value = ["ns1.example.com."]
        mock_append.return_value = True

        result = fixer.fix_zone("example.com")

        assert result.status == "changed"

    @patch.object(DNSNSFixer, "_append_zone")
    @patch.object(DNSNSFixer, "get_zone_ns")
    def test_fix_zone_append_unchanged(self, mock_get_ns, mock_append):
        fixer = DNSNSFixer(
            ns1="ns1.example.com",
            ns2="ns2.example.com",
            mode=NSFixMode.APPEND,
        )
        mock_get_ns.return_value = ["ns1.example.com.", "ns2.example.com."]

        result = fixer.fix_zone("example.com")

        assert result.status == "unchanged"
        mock_append.assert_not_called()

    @patch.object(DNSNSFixer, "fix_zone")
    def test_fix_all_zones_explicit(self, mock_fix, fixer):
        mock_fix.side_effect = [
            fixer.fix_zone("example.com") if False else None,
        ]
        mock_fix.side_effect = [
            type("R", (), {"status": "changed"})(),
            type("R", (), {"status": "unchanged"})(),
        ]

        results = fixer.fix_all_zones(["example.com", "test.org"])

        assert len(results) == 2
        assert mock_fix.call_count == 2

    @patch.object(DNSNSFixer, "list_zones")
    @patch.object(DNSNSFixer, "fix_zone")
    def test_fix_all_zones_discovery(self, mock_fix, mock_list, fixer):
        mock_list.return_value = ["example.com"]
        mock_fix.return_value = type("R", (), {"status": "changed"})()

        results = fixer.fix_all_zones()

        assert len(results) == 1

    def test_get_summary(self, fixer):
        result_changed = type("R", (), {"status": "changed"})()
        result_unchanged = type("R", (), {"status": "unchanged"})()
        result_failed = type("R", (), {"status": "failed"})()

        summary = fixer.get_summary([result_changed, result_unchanged, result_failed])

        assert summary["total"] == 3
        assert summary["changed"] == 1
        assert summary["unchanged"] == 1
        assert summary["failed"] == 1
        assert summary["mode"] == "enforce"
