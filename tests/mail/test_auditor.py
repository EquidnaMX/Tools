"""Tests for mail auditor module."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from tools.mail.auditor import (
    ReputationCheck,
    DomainAuditResult,
    AuditReport,
    MailAuditor,
)
from tools.mail.dns_validator import DNSValidation
from tools.mail.service_monitor import ServiceStatus, ServiceState


# ============================================================================
# DATACLASS TESTS
# ============================================================================


class TestReputationCheck:
    """Tests for ReputationCheck dataclass."""
    
    def test_reputation_check_init_clean(self):
        """Test ReputationCheck initialization for clean IP."""
        check = ReputationCheck(rbl_name="zen.spamhaus.org")
        
        assert check.rbl_name == "zen.spamhaus.org"
        assert check.listed is False
        assert check.response == ""
    
    def test_reputation_check_init_listed(self):
        """Test ReputationCheck initialization for listed IP."""
        check = ReputationCheck(
            rbl_name="bl.spamcop.net",
            listed=True,
            response="127.0.0.2",
        )
        
        assert check.rbl_name == "bl.spamcop.net"
        assert check.listed is True
        assert check.response == "127.0.0.2"
    
    def test_reputation_check_to_dict_clean(self):
        """Test to_dict for clean IP."""
        check = ReputationCheck(rbl_name="zen.spamhaus.org")
        result = check.to_dict()
        
        assert result["rbl"] == "zen.spamhaus.org"
        assert result["status"] == "clean"
        assert result["response"] == ""
    
    def test_reputation_check_to_dict_listed(self):
        """Test to_dict for listed IP."""
        check = ReputationCheck(
            rbl_name="bl.spamcop.net",
            listed=True,
            response="127.0.0.2",
        )
        result = check.to_dict()
        
        assert result["rbl"] == "bl.spamcop.net"
        assert result["status"] == "listed"
        assert result["response"] == "127.0.0.2"


class TestDomainAuditResult:
    """Tests for DomainAuditResult dataclass."""
    
    def test_domain_audit_result_init(self):
        """Test DomainAuditResult initialization."""
        result = DomainAuditResult(domain="example.com")
        
        assert result.domain == "example.com"
        assert result.dns_validation is None
        assert result.sympa_robot == "not_configured"
        assert result.sympa_aliases == "missing"
    
    def test_domain_audit_result_to_dict_minimal(self):
        """Test to_dict with minimal data."""
        result = DomainAuditResult(domain="example.com")
        data = result.to_dict()
        
        assert data["domain"] == "example.com"
        assert "records" not in data
        assert data["sympa"]["robot"] == "not_configured"
        assert data["sympa"]["aliases_in_etc_aliases"] == "missing"
    
    def test_domain_audit_result_to_dict_with_dns(self):
        """Test to_dict with DNS validation data."""
        dns_val = DNSValidation(
            domain="example.com",
            has_mx=True,
            mx_records=["mail.example.com"],
        )
        
        result = DomainAuditResult(
            domain="example.com",
            dns_validation=dns_val,
        )
        data = result.to_dict()
        
        assert data["domain"] == "example.com"
        assert "records" in data
        assert data["records"]["MX"]  # Has MX record in format "mail.example.com"


class TestAuditReport:
    """Tests for AuditReport dataclass."""
    
    def test_audit_report_init(self):
        """Test AuditReport initialization."""
        report = AuditReport()
        
        assert isinstance(report.timestamp, datetime)
        assert report.server_ip == ""
        assert report.server_hostname == ""
        assert len(report.services) == 0
        assert len(report.domains) == 0
        assert len(report.reputation) == 0
    
    def test_audit_report_to_dict(self):
        """Test AuditReport to_dict conversion."""
        report = AuditReport(
            server_ip="192.168.1.100",
            server_hostname="mail.example.com",
            ptr_record="mail.example.com",
            ptr_target="mail.example.com",
            ptr_status="ok",
        )
        
        # Add service status
        report.services["postfix"] = ServiceStatus(
            name="postfix",
            state=ServiceState.ACTIVE,
        )
        
        # Add domain result
        report.domains.append(DomainAuditResult(domain="example.com"))
        
        # Add reputation check
        report.reputation.append(ReputationCheck(rbl_name="zen.spamhaus.org"))
        
        data = report.to_dict()
        
        assert data["server"]["ip"] == "192.168.1.100"
        assert data["server"]["hostname"] == "mail.example.com"
        assert data["server"]["ptr_status"] == "ok"
        assert data["server"]["services"]["postfix"] == "active"
        assert data["summary"]["total_domains"] == 1
        assert data["summary"]["services_active"] == 1
        assert data["reputation"]["zen.spamhaus.org"] == "clean"


# ============================================================================
# MAIL AUDITOR TESTS
# ============================================================================


class TestMailAuditor:
    """Tests for MailAuditor class."""
    
    @pytest.fixture
    def auditor(self):
        """Create MailAuditor instance for testing."""
        return MailAuditor(
            ptr_target="mail.example.com",
            dkim_selector="default",
            timeout=5,
            include_rbls=True,
        )
    
    def test_auditor_init(self, auditor):
        """Test MailAuditor initialization."""
        assert auditor.ptr_target == "mail.example.com"
        assert auditor.dkim_selector == "default"
        assert auditor.timeout == 5
        assert auditor.include_rbls is True
        assert auditor.dns_validator is not None
        assert auditor.service_monitor is not None
    
    @patch("subprocess.run")
    def test_run_command_success(self, mock_run, auditor):
        """Test _run_command with successful execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output data\n",
        )
        
        result = auditor._run_command(["test", "command"])
        
        assert result == "output data"
        mock_run.assert_called_once()
    
    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run, auditor):
        """Test _run_command with failed execution."""
        mock_run.return_value = MagicMock(returncode=1)
        
        result = auditor._run_command(["test", "command"])
        
        assert result == ""
    
    @patch("subprocess.run")
    def test_run_command_timeout(self, mock_run, auditor):
        """Test _run_command with timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)
        
        result = auditor._run_command(["test", "command"])
        
        assert result == ""
    
    @patch("socket.gethostbyname")
    @patch("socket.gethostname")
    @patch.object(MailAuditor, "_run_command")
    def test_get_server_ip_hostname_i(self, mock_run, mock_hostname, mock_gethost, auditor):
        """Test get_server_ip using hostname -I."""
        mock_run.return_value = "192.168.1.100 10.0.0.1 "
        
        ip = auditor.get_server_ip()
        
        assert ip == "192.168.1.100"
        mock_run.assert_called_once_with(["hostname", "-I"])
    
    @patch("socket.gethostbyname")
    @patch("socket.gethostname")
    @patch.object(MailAuditor, "_run_command")
    def test_get_server_ip_socket_fallback(self, mock_run, mock_hostname, mock_gethost, auditor):
        """Test get_server_ip with socket fallback."""
        mock_run.return_value = ""
        mock_hostname.return_value = "mail.example.com"
        mock_gethost.return_value = "192.168.1.100"
        
        ip = auditor.get_server_ip()
        
        assert ip == "192.168.1.100"
        mock_hostname.assert_called_once()
        mock_gethost.assert_called_once_with("mail.example.com")
    
    @patch("socket.getfqdn")
    def test_get_server_hostname(self, mock_fqdn, auditor):
        """Test get_server_hostname."""
        mock_fqdn.return_value = "mail.example.com"
        
        hostname = auditor.get_server_hostname()
        
        assert hostname == "mail.example.com"
        mock_fqdn.assert_called_once()
    
    @patch.object(MailAuditor, "_run_command")
    def test_discover_domains_from_postfix(self, mock_run, auditor):
        """Test discover_domains_from_postfix."""
        def run_side_effect(cmd):
            if "mydestination" in cmd:
                return "localhost, example.com, mail.example.com"
            elif "virtual_mailbox_domains" in cmd:
                return "domain1.com domain2.com"
            else:
                return ""
        
        mock_run.side_effect = run_side_effect
        
        domains = auditor.discover_domains_from_postfix()
        
        assert "example.com" in domains
        assert "mail.example.com" in domains
        assert "domain1.com" in domains
        assert "domain2.com" in domains
        assert "localhost" not in domains  # Not a valid domain format
    
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_discover_domains_from_opendkim(self, mock_exists, mock_read, auditor):
        """Test discover_domains_from_opendkim."""
        mock_exists.return_value = True
        mock_read.return_value = """
# OpenDKIM signing table
*@example.com default._domainkey.example.com
*@test.org selector1._domainkey.test.org
"""
        
        domains = auditor.discover_domains_from_opendkim()
        
        assert "example.com" in domains
        assert "test.org" in domains
        assert len(domains) == 2
    
    @patch("pathlib.Path.iterdir")
    @patch("pathlib.Path.is_dir")
    @patch("pathlib.Path.exists")
    def test_discover_domains_from_sympa_new_layout(self, mock_exists, mock_is_dir, mock_iterdir, auditor):
        """Test discover_domains_from_sympa with new layout."""
        # Mock /etc/sympa/domains/ directory
        domain1 = MagicMock()
        domain1.is_dir.return_value = True
        domain1.name = "lists.example.com"
        
        domain2 = MagicMock()
        domain2.is_dir.return_value = True
        domain2.name = "lists.test.org"
        
        mock_exists.return_value = True
        mock_is_dir.return_value = True
        mock_iterdir.return_value = [domain1, domain2]
        
        domains = auditor.discover_domains_from_sympa()
        
        assert "lists.example.com" in domains
        assert "lists.test.org" in domains
    
    @patch.object(MailAuditor, "discover_domains_from_sympa")
    @patch.object(MailAuditor, "discover_domains_from_opendkim")
    @patch.object(MailAuditor, "discover_domains_from_postfix")
    def test_discover_all_domains(self, mock_postfix, mock_opendkim, mock_sympa, auditor):
        """Test discover_all_domains combines all sources."""
        mock_postfix.return_value = {"example.com", "mail.example.com"}
        mock_opendkim.return_value = {"example.com", "test.org"}
        mock_sympa.return_value = {"lists.example.com"}
        
        domains = auditor.discover_all_domains()
        
        assert "example.com" in domains
        assert "mail.example.com" in domains
        assert "test.org" in domains
        assert "lists.example.com" in domains
        assert len(domains) == 4
    
    @patch("pathlib.Path.exists")
    def test_check_sympa_robot_new_layout(self, mock_exists, auditor):
        """Test check_sympa_robot with new layout."""
        mock_exists.return_value = True
        
        status = auditor.check_sympa_robot("lists.example.com")
        assert status == "configured"
    
    @patch("pathlib.Path.exists")
    def test_check_sympa_robot_legacy_layout(self, mock_exists, auditor):
        """Test check_sympa_robot with legacy layout."""
        # First call for new layout returns False, second for legacy returns True
        mock_exists.side_effect = [False, True]
        
        status = auditor.check_sympa_robot("lists.example.com")
        assert status == "configured"
    
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_check_sympa_aliases(self, mock_exists, mock_read, auditor):
        """Test check_sympa_aliases."""
        mock_exists.return_value = True
        mock_read.return_value = """
# Sympa aliases
sympa: "| /usr/lib/sympa/bin/queue sympa@mail.example.com"
listmaster: "| /usr/lib/sympa/bin/queue listmaster@mail.example.com"
"""
        
        status = auditor.check_sympa_aliases()
        assert status == "present"
    
    @patch("subprocess.run")
    def test_check_ip_reputation_clean(self, mock_run, auditor):
        """Test check_ip_reputation with clean IP."""
        mock_run.return_value = MagicMock(
            returncode=2,  # NXDOMAIN = not listed
            stdout="",
        )
        
        results = auditor.check_ip_reputation("192.168.1.100")
        
        assert len(results) == 3  # Three default RBLs
        assert all(not r.listed for r in results)
    
    @patch("subprocess.run")
    def test_check_ip_reputation_listed(self, mock_run, auditor):
        """Test check_ip_reputation with listed IP."""
        def run_side_effect(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "zen.spamhaus.org" in cmd_str:
                return MagicMock(returncode=0, stdout="100.1.168.192.zen.spamhaus.org.\t300\tIN\tA\t127.0.0.2\n")
            else:
                return MagicMock(returncode=2, stdout="")
        
        mock_run.side_effect = run_side_effect
        
        results = auditor.check_ip_reputation("192.168.1.100")
        
        assert len(results) == 3
        listed = [r for r in results if r.listed]
        assert len(listed) == 1
        assert listed[0].rbl_name == "zen.spamhaus.org"
    
    @patch.object(MailAuditor, "check_sympa_robot")
    def test_audit_domain(self, mock_sympa, auditor):
        """Test audit_domain."""
        mock_sympa.return_value = "configured_new"
        
        with patch.object(auditor.dns_validator, "validate_domain") as mock_validate:
            mock_validate.return_value = DNSValidation(domain="example.com", has_mx=True)
            
            result = auditor.audit_domain("example.com", "192.168.1.100")
            
            assert result.domain == "example.com"
            assert result.dns_validation is not None
            assert result.sympa_robot == "configured_new"
    
    @patch.object(MailAuditor, "check_ip_reputation")
    @patch.object(MailAuditor, "check_sympa_aliases")
    @patch.object(MailAuditor, "audit_domain")
    @patch.object(MailAuditor, "discover_all_domains")
    @patch.object(MailAuditor, "get_server_hostname")
    @patch.object(MailAuditor, "get_server_ip")
    def test_audit_server(
        self,
        mock_ip,
        mock_hostname,
        mock_discover,
        mock_audit_domain,
        mock_aliases,
        mock_reputation,
        auditor,
    ):
        """Test audit_server complete flow."""
        mock_ip.return_value = "192.168.1.100"
        mock_hostname.return_value = "mail.example.com"
        mock_discover.return_value = {"example.com", "test.org"}
        mock_audit_domain.return_value = DomainAuditResult(domain="example.com")
        mock_aliases.return_value = "present"
        mock_reputation.return_value = [ReputationCheck(rbl_name="zen.spamhaus.org")]
        
        with patch.object(auditor.service_monitor, "check_all_services") as mock_services:
            mock_services.return_value = {
                "postfix": ServiceStatus(name="postfix", state=ServiceState.ACTIVE)
            }
            
            with patch.object(auditor.service_monitor, "check_apache_sympa_config") as mock_apache:
                mock_apache.return_value = {"apache2": "active", "sympa_fcgi": "enabled"}
                
                with patch.object(auditor.dns_validator, "get_ptr_record") as mock_ptr:
                    mock_ptr.return_value = "mail.example.com"
                    
                    report = auditor.audit_server()
                    
                    assert report.server_ip == "192.168.1.100"
                    assert report.server_hostname == "mail.example.com"
                    assert len(report.domains) == 2
                    assert len(report.services) == 1
                    assert len(report.reputation) == 1
