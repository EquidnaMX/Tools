"""Tests for domain health checker module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.mail.domain_health import (
    ConnectivityCheck,
    DomainHealth,
    DomainHealthChecker,
)
from tools.mail.dns_validator import DNSValidation


# ============================================================================
# DATACLASS TESTS
# ============================================================================


class TestConnectivityCheck:
    """Tests for ConnectivityCheck dataclass."""
    
    def test_connectivity_check_init_unreachable(self):
        """Test ConnectivityCheck initialization for unreachable host."""
        check = ConnectivityCheck(host="mail.example.com")
        
        assert check.host == "mail.example.com"
        assert check.port == 25
        assert check.reachable is False
        assert check.response_time is None
    
    def test_connectivity_check_init_reachable(self):
        """Test ConnectivityCheck initialization for reachable host."""
        check = ConnectivityCheck(
            host="mail.example.com",
            port=587,
            reachable=True,
            response_time=45.2,
        )
        
        assert check.host == "mail.example.com"
        assert check.port == 587
        assert check.reachable is True
        assert check.response_time == 45.2
    
    def test_connectivity_check_to_dict(self):
        """Test ConnectivityCheck to_dict conversion."""
        check = ConnectivityCheck(
            host="mail.example.com",
            port=25,
            reachable=True,
            response_time=32.5,
        )
        
        result = check.to_dict()
        
        assert result["host"] == "mail.example.com"
        assert result["port"] == 25
        assert result["reachable"] is True
        assert result["response_time_ms"] == 32.5


class TestDomainHealth:
    """Tests for DomainHealth dataclass."""
    
    def test_domain_health_init(self):
        """Test DomainHealth initialization."""
        health = DomainHealth(domain="example.com", selector="default")
        
        assert health.domain == "example.com"
        assert health.selector == "default"
        assert health.has_mx is False
        assert health.has_spf is False
        assert health.has_dkim is False
        assert health.has_dmarc is False
        assert health.mx_reachable is False
        assert health.score == 0
        assert len(health.issues) == 0
    
    def test_calculate_score_perfect(self):
        """Test calculate_score with perfect health."""
        health = DomainHealth(
            domain="example.com",
            has_mx=True,
            has_spf=True,
            has_dkim=True,
            has_dmarc=True,
            mx_reachable=True,
        )
        
        score = health.calculate_score()
        
        assert score == 100
        assert health.score == 100
        assert len(health.issues) == 0
    
    def test_calculate_score_partial(self):
        """Test calculate_score with partial health."""
        health = DomainHealth(
            domain="example.com",
            has_mx=True,
            has_spf=True,
            has_dkim=False,
            has_dmarc=False,
            mx_reachable=True,
        )
        
        score = health.calculate_score()
        
        # MX(25) + SPF(25) + Connectivity(15) = 65
        assert score == 65
        assert health.score == 65
        assert "Missing DKIM record" in health.issues
        assert "Missing DMARC record" in health.issues
    
    def test_calculate_score_poor(self):
        """Test calculate_score with poor health."""
        health = DomainHealth(
            domain="example.com",
            has_mx=False,
            has_spf=False,
            has_dkim=False,
            has_dmarc=False,
            mx_reachable=False,
        )
        
        score = health.calculate_score()
        
        assert score == 0
        assert health.score == 0
        assert len(health.issues) == 5
        assert "Missing MX records" in health.issues
        assert "Missing SPF record" in health.issues
        assert "MX servers not reachable" in health.issues
    
    def test_domain_health_to_dict(self):
        """Test DomainHealth to_dict conversion."""
        health = DomainHealth(
            domain="example.com",
            selector="default",
            has_mx=True,
            has_spf=True,
            mx_hosts=["mail1.example.com", "mail2.example.com"],
        )
        health.calculate_score()
        
        result = health.to_dict()
        
        assert result["domain"] == "example.com"
        assert result["selector"] == "default"
        assert result["checks"]["has_mx"] is True
        assert result["checks"]["has_spf"] is True
        assert result["mx_hosts"] == ["mail1.example.com", "mail2.example.com"]
        assert "score" in result
        assert "issues" in result


# ============================================================================
# DOMAIN HEALTH CHECKER TESTS
# ============================================================================


class TestDomainHealthChecker:
    """Tests for DomainHealthChecker class."""
    
    @pytest.fixture
    def checker(self):
        """Create DomainHealthChecker instance for testing."""
        return DomainHealthChecker(timeout=4, check_connectivity=True)
    
    def test_checker_init(self, checker):
        """Test DomainHealthChecker initialization."""
        assert checker.timeout == 4
        assert checker.check_connectivity is True
        assert checker.dns_validator is not None
    
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_parse_opendkim_signing_table(self, mock_exists, mock_read, checker):
        """Test parse_opendkim_signing_table."""
        mock_exists.return_value = True
        mock_read.return_value = """
# OpenDKIM signing table
*@example.com default._domainkey.example.com
*@test.org selector1._domainkey.test.org
# Comment line
*@mail.net s2024._domainkey.mail.net
"""
        
        selectors = checker.parse_opendkim_signing_table(
            Path("/etc/opendkim/signing.table")
        )
        
        assert selectors["example.com"] == "default"
        assert selectors["test.org"] == "selector1"
        assert selectors["mail.net"] == "s2024"
        assert len(selectors) == 3
    
    @patch("pathlib.Path.exists")
    def test_parse_opendkim_signing_table_not_found(self, mock_exists, checker):
        """Test parse_opendkim_signing_table with missing file."""
        mock_exists.return_value = False
        
        selectors = checker.parse_opendkim_signing_table()
        
        assert len(selectors) == 0
    
    @patch("subprocess.run")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_parse_opendkim_signing_table_from_postconf(
        self, mock_exists, mock_read, mock_run, checker
    ):
        """Test parse_opendkim_signing_table with postconf lookup."""
        # postconf returns path
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="refile:/etc/opendkim/signing.table\n",
        )
        
        mock_exists.return_value = True
        mock_read.return_value = "*@example.com default._domainkey.example.com\n"
        
        selectors = checker.parse_opendkim_signing_table()
        
        assert "example.com" in selectors
    
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_parse_opendkim_key_table(self, mock_exists, mock_read, checker):
        """Test parse_opendkim_key_table."""
        mock_exists.return_value = True
        mock_read.return_value = """
# OpenDKIM key table
default._domainkey.example.com example.com:default:/etc/opendkim/keys/example.com/default.private
selector1._domainkey.test.org test.org:selector1:/etc/opendkim/keys/test.org/selector1.private
"""
        
        selectors = checker.parse_opendkim_key_table(
            Path("/etc/opendkim/key.table")
        )
        
        assert selectors["example.com"] == "default"
        assert selectors["test.org"] == "selector1"
    
    @patch("pathlib.Path.exists")
    def test_parse_opendkim_key_table_not_found(self, mock_exists, checker):
        """Test parse_opendkim_key_table with missing file."""
        mock_exists.return_value = False
        
        selectors = checker.parse_opendkim_key_table()
        
        assert len(selectors) == 0
    
    @patch.object(DomainHealthChecker, "parse_opendkim_key_table")
    @patch.object(DomainHealthChecker, "parse_opendkim_signing_table")
    def test_get_domain_selector_from_signing_table(
        self, mock_signing, mock_key, checker
    ):
        """Test get_domain_selector from signing table."""
        mock_signing.return_value = {"example.com": "selector2024"}
        mock_key.return_value = {}
        
        selector = checker.get_domain_selector("example.com")
        
        assert selector == "selector2024"
    
    @patch.object(DomainHealthChecker, "parse_opendkim_key_table")
    @patch.object(DomainHealthChecker, "parse_opendkim_signing_table")
    def test_get_domain_selector_from_key_table_fallback(
        self, mock_signing, mock_key, checker
    ):
        """Test get_domain_selector fallback to key table."""
        mock_signing.return_value = {}
        mock_key.return_value = {"example.com": "key_selector"}
        
        selector = checker.get_domain_selector("example.com")
        
        assert selector == "key_selector"
    
    @patch.object(DomainHealthChecker, "parse_opendkim_key_table")
    @patch.object(DomainHealthChecker, "parse_opendkim_signing_table")
    def test_get_domain_selector_default(self, mock_signing, mock_key, checker):
        """Test get_domain_selector returns default when not found."""
        mock_signing.return_value = {}
        mock_key.return_value = {}
        
        selector = checker.get_domain_selector("example.com")
        
        assert selector == "default"
    
    def test_get_domain_selector_with_provided_selectors(self, checker):
        """Test get_domain_selector with pre-parsed selectors."""
        selectors = {"example.com": "provided_selector"}
        
        selector = checker.get_domain_selector("example.com", selectors)
        
        assert selector == "provided_selector"
    
    @patch("subprocess.run")
    def test_check_smtp_connectivity_reachable_nc(self, mock_run, checker):
        """Test check_smtp_connectivity with netcat (reachable)."""
        mock_run.return_value = MagicMock(returncode=0)
        
        result = checker.check_smtp_connectivity("mail.example.com", 25)
        
        assert result.host == "mail.example.com"
        assert result.port == 25
        assert result.reachable is True
        assert result.response_time is not None
        assert result.response_time >= 0
    
    @patch("subprocess.run")
    def test_check_smtp_connectivity_unreachable_nc(self, mock_run, checker):
        """Test check_smtp_connectivity with netcat (unreachable)."""
        mock_run.return_value = MagicMock(returncode=1)
        
        result = checker.check_smtp_connectivity("mail.example.com", 25)
        
        assert result.host == "mail.example.com"
        assert result.port == 25
        assert result.reachable is False
    
    @patch("socket.socket")
    @patch("subprocess.run")
    def test_check_smtp_connectivity_socket_fallback(self, mock_run, mock_socket, checker):
        """Test check_smtp_connectivity with socket fallback."""
        # nc not available
        mock_run.side_effect = FileNotFoundError()
        
        # Socket connection succeeds
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance
        
        result = checker.check_smtp_connectivity("mail.example.com", 25)
        
        assert result.reachable is True
        mock_sock_instance.settimeout.assert_called_once_with(4)
        mock_sock_instance.close.assert_called_once()
    
    @patch("socket.socket")
    @patch("subprocess.run")
    def test_check_smtp_connectivity_socket_fail(self, mock_run, mock_socket, checker):
        """Test check_smtp_connectivity with socket connection failure."""
        mock_run.side_effect = FileNotFoundError()
        
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 1  # Connection failed
        mock_socket.return_value = mock_sock_instance
        
        result = checker.check_smtp_connectivity("mail.example.com", 25)
        
        assert result.reachable is False
    
    @patch.object(DomainHealthChecker, "check_smtp_connectivity")
    @patch.object(DomainHealthChecker, "get_domain_selector")
    def test_check_domain_health_full(
        self, mock_selector, mock_connectivity, checker
    ):
        """Test check_domain_health with full validation."""
        mock_selector.return_value = "selector2024"
        
        # Mock connectivity check
        mock_connectivity.return_value = ConnectivityCheck(
            host="mail.example.com",
            port=25,
            reachable=True,
            response_time=25.5,
        )
        
        # Mock DNS methods directly
        with patch.object(checker.dns_validator, "get_mx_records") as mock_mx:
            mock_mx.return_value = ["10 mail.example.com"]
            
            with patch.object(checker.dns_validator, "get_spf_record") as mock_spf:
                mock_spf.return_value = "v=spf1 include:_spf.example.com ~all"
                
                with patch.object(checker.dns_validator, "get_dkim_record") as mock_dkim:
                    mock_dkim.return_value = "v=DKIM1; k=rsa; p=MIGfMA0GCS..."
                    
                    with patch.object(checker.dns_validator, "get_dmarc_record") as mock_dmarc:
                        mock_dmarc.return_value = "v=DMARC1; p=reject; rua=mailto:dmarc@example.com"
                        
                        health = checker.check_domain_health("example.com")
            
            assert health.domain == "example.com"
            assert health.selector == "selector2024"
            assert health.has_mx is True
            assert health.has_spf is True
            assert health.has_dkim is True
            assert health.has_dmarc is True
            assert health.mx_reachable is True
            assert len(health.mx_hosts) == 1
            assert health.mx_hosts[0] == "mail.example.com"
            assert health.score > 0
    
    @patch.object(DomainHealthChecker, "check_smtp_connectivity")
    @patch.object(DomainHealthChecker, "get_domain_selector")
    def test_check_domain_health_no_connectivity_check(
        self, mock_selector, mock_connectivity, checker
    ):
        """Test check_domain_health without connectivity checks."""
        checker.check_connectivity = False
        mock_selector.return_value = "default"
        
        with patch.object(checker.dns_validator, "validate_domain") as mock_validate:
            dns_val = DNSValidation(
                domain="example.com",
                has_mx=True,
                mx_records=["mail.example.com"],
            )
            mock_validate.return_value = dns_val
            
            health = checker.check_domain_health("example.com")
            
            assert health.domain == "example.com"
            assert len(health.connectivity) == 0
            mock_connectivity.assert_not_called()
    
    @patch.object(DomainHealthChecker, "get_domain_selector")
    def test_check_domain_health_no_mx_records(self, mock_selector, checker):
        """Test check_domain_health when no MX records found."""
        checker.check_connectivity = False
        mock_selector.return_value = "default"
        
        with patch.object(checker.dns_validator, "validate_domain") as mock_validate:
            dns_val = DNSValidation(
                domain="example.com",
                has_mx=False,
                mx_records=[],
            )
            mock_validate.return_value = dns_val
            
            health = checker.check_domain_health("example.com")
            
            assert health.has_mx is False
            assert len(health.mx_hosts) == 0
            assert health.mx_reachable is False
    
    @patch.object(DomainHealthChecker, "check_domain_health")
    def test_check_multiple_domains(self, mock_check, checker):
        """Test check_multiple_domains."""
        # Create different health results for each domain
        health1 = DomainHealth(domain="example.com", has_mx=True, has_spf=True)
        health1.calculate_score()
        
        health2 = DomainHealth(domain="test.org", has_mx=True)
        health2.calculate_score()
        
        mock_check.side_effect = [health1, health2]
        
        results = checker.check_multiple_domains(["example.com", "test.org"])
        
        assert len(results) == 2
        assert results[0].domain == "example.com"
        assert results[1].domain == "test.org"
        assert mock_check.call_count == 2
    
    def test_get_summary_empty(self, checker):
        """Test get_summary with empty results."""
        summary = checker.get_summary([])
        
        assert summary["total_domains"] == 0
        assert summary["healthy"] == 0
        assert summary["warnings"] == 0
        assert summary["critical"] == 0
    
    def test_get_summary_mixed_results(self, checker):
        """Test get_summary with mixed health results."""
        health1 = DomainHealth(domain="good.com", score=95)
        health2 = DomainHealth(domain="warning.com", score=65)
        health3 = DomainHealth(domain="critical.com", score=35)
        health4 = DomainHealth(domain="perfect.com", score=100)
        
        results = [health1, health2, health3, health4]
        summary = checker.get_summary(results)
        
        assert summary["total_domains"] == 4
        assert summary["average_score"] == 73.8  # (95+65+35+100)/4 rounded by get_summary
        assert summary["healthy"] == 2  # >= 80
        assert summary["warnings"] == 1  # 50-79
        assert summary["critical"] == 1  # < 50
    
    def test_get_summary_score_boundaries(self, checker):
        """Test get_summary score boundary conditions."""
        health1 = DomainHealth(domain="boundary80.com", score=80)
        health2 = DomainHealth(domain="boundary50.com", score=50)
        health3 = DomainHealth(domain="boundary49.com", score=49)
        
        results = [health1, health2, health3]
        summary = checker.get_summary(results)
        
        assert summary["healthy"] == 1  # score == 80
        assert summary["warnings"] == 1  # score == 50
        assert summary["critical"] == 1  # score == 49
