"""Tests for DNSValidator module."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from tools.mail.dns_validator import DNSValidator, DNSValidation


class TestDNSValidation:
    """Test DNSValidation dataclass."""
    
    def test_dns_validation_initialization(self):
        """Test DNSValidation initialization."""
        validation = DNSValidation(domain="example.com")
        
        assert validation.domain == "example.com"
        assert validation.mx_records == []
        assert validation.a_record == ""
        assert validation.spf_record == ""
        assert validation.dkim_record == ""
        assert validation.dmarc_record == ""
        assert validation.has_mx is False
        assert validation.has_spf is False
        assert validation.has_dkim is False
        assert validation.has_dmarc is False
    
    def test_dns_validation_to_dict(self):
        """Test DNSValidation to_dict method."""
        validation = DNSValidation(
            domain="example.com",
            mx_records=["10 mail.example.com"],
            a_record="1.2.3.4",
            spf_record="v=spf1 mx ~all",
            has_mx=True,
            has_spf=True,
        )
        
        result = validation.to_dict()
        
        assert result["domain"] == "example.com"
        assert result["records"]["MX"] == "10 mail.example.com"
        assert result["records"]["A_mail"] == "1.2.3.4"
        assert result["records"]["SPF"] == "v=spf1 mx ~all"
        assert result["validation"]["has_mx"] is True
        assert result["validation"]["has_spf"] is True


class TestDNSValidator:
    """Test DNSValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create DNSValidator instance for testing."""
        return DNSValidator(timeout=2, retries=1)
    
    def test_validator_initialization(self, validator):
        """Test DNSValidator initialization."""
        assert validator.timeout == 2
        assert validator.retries == 1
        assert validator.dkim_selector == "default"
    
    @patch("subprocess.run")
    def test_dig_query_success(self, mock_run, validator):
        """Test successful dig query."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1.2.3.4\n",
            stderr="",
        )
        
        result = validator._dig_query("example.com", "A")
        
        assert result == "1.2.3.4"
        assert mock_run.called
        
        # Verify dig command structure
        call_args = mock_run.call_args[0][0]
        assert "dig" in call_args
        assert "+time=2" in call_args
        assert "+tries=1" in call_args
        assert "example.com" in call_args
        assert "A" in call_args
    
    @patch("subprocess.run")
    def test_dig_query_timeout(self, mock_run, validator):
        """Test dig query timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("dig", 2)
        
        result = validator._dig_query("example.com", "A")
        
        assert result == ""
    
    @patch("subprocess.run")
    def test_dig_query_command_not_found(self, mock_run, validator):
        """Test dig command not found."""
        mock_run.side_effect = FileNotFoundError()
        
        result = validator._dig_query("example.com", "A")
        
        assert result == ""
    
    @patch("subprocess.run")
    def test_get_mx_records(self, mock_run, validator):
        """Test MX record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="example.com. 300 IN MX 10 mail1.example.com.\nexample.com. 300 IN MX 20 mail2.example.com.\n",
            stderr="",
        )
        
        mx_records = validator.get_mx_records("example.com")
        
        assert len(mx_records) == 2
        assert "10 mail1.example.com" in mx_records
        assert "20 mail2.example.com" in mx_records
        # Check sorting by priority
        assert mx_records[0].startswith("10")
        assert mx_records[1].startswith("20")
    
    @patch("subprocess.run")
    def test_get_mx_records_empty(self, mock_run, validator):
        """Test MX record retrieval with no results."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        
        mx_records = validator.get_mx_records("example.com")
        
        assert mx_records == []
    
    @patch("subprocess.run")
    def test_get_a_record(self, mock_run, validator):
        """Test A record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1.2.3.4\n",
            stderr="",
        )
        
        a_record = validator.get_a_record("mail.example.com")
        
        assert a_record == "1.2.3.4"
    
    @patch("subprocess.run")
    def test_get_spf_record(self, mock_run, validator):
        """Test SPF record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"v=spf1 mx a ~all"\n',
            stderr="",
        )
        
        spf = validator.get_spf_record("example.com")
        
        assert "v=spf1" in spf
        assert "mx" in spf
    
    @patch("subprocess.run")
    def test_get_spf_record_not_found(self, mock_run, validator):
        """Test SPF record not found."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"some other TXT record"\n',
            stderr="",
        )
        
        spf = validator.get_spf_record("example.com")
        
        assert spf == ""
    
    @patch("subprocess.run")
    def test_get_dkim_record(self, mock_run, validator):
        """Test DKIM record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"v=DKIM1; k=rsa; p=MIGfMA0GCS..."\n',
            stderr="",
        )
        
        dkim = validator.get_dkim_record("example.com", "default")
        
        assert "v=DKIM1" in dkim
        assert "k=rsa" in dkim
    
    @patch("subprocess.run")
    def test_get_dmarc_record(self, mock_run, validator):
        """Test DMARC record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"\n',
            stderr="",
        )
        
        dmarc = validator.get_dmarc_record("example.com")
        
        assert "v=DMARC1" in dmarc
        assert "p=quarantine" in dmarc
    
    @patch("subprocess.run")
    def test_get_ptr_record(self, mock_run, validator):
        """Test PTR record retrieval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="mail.example.com.\n",
            stderr="",
        )
        
        ptr = validator.get_ptr_record("1.2.3.4")
        
        assert ptr == "mail.example.com"
    
    @patch.object(DNSValidator, "get_mx_records")
    @patch.object(DNSValidator, "get_a_record")
    @patch.object(DNSValidator, "get_spf_record")
    @patch.object(DNSValidator, "get_dkim_record")
    @patch.object(DNSValidator, "get_dmarc_record")
    @patch.object(DNSValidator, "get_ptr_record")
    def test_validate_domain_complete(
        self,
        mock_ptr,
        mock_dmarc,
        mock_dkim,
        mock_spf,
        mock_a,
        mock_mx,
        validator,
    ):
        """Test complete domain validation."""
        # Setup mocks
        mock_mx.return_value = ["10 mail.example.com"]
        mock_a.return_value = "1.2.3.4"
        mock_spf.return_value = "v=spf1 mx ~all"
        mock_dkim.return_value = "v=DKIM1; k=rsa; p=..."
        mock_dmarc.return_value = "v=DMARC1; p=quarantine"
        mock_ptr.return_value = "mail.example.com"
        
        validation = validator.validate_domain(
            domain="example.com",
            selector="default",
            expected_ptr="mail.example.com",
            server_ip="1.2.3.4",
        )
        
        assert validation.domain == "example.com"
        assert validation.has_mx is True
        assert validation.has_spf is True
        assert validation.has_dkim is True
        assert validation.has_dmarc is True
        assert validation.ptr_matches is True
        assert len(validation.errors) == 0
    
    @patch.object(DNSValidator, "get_mx_records")
    @patch.object(DNSValidator, "get_a_record")
    @patch.object(DNSValidator, "get_spf_record")
    @patch.object(DNSValidator, "get_dkim_record")
    @patch.object(DNSValidator, "get_dmarc_record")
    def test_validate_domain_with_errors(
        self,
        mock_dmarc,
        mock_dkim,
        mock_spf,
        mock_a,
        mock_mx,
        validator,
    ):
        """Test domain validation with missing records."""
        # Setup mocks - missing SPF and DKIM
        mock_mx.return_value = ["10 mail.example.com"]
        mock_a.return_value = "1.2.3.4"
        mock_spf.return_value = ""
        mock_dkim.return_value = ""
        mock_dmarc.return_value = ""
        
        validation = validator.validate_domain(domain="example.com")
        
        assert validation.has_mx is True
        assert validation.has_spf is False
        assert validation.has_dkim is False
        assert validation.has_dmarc is False
        assert len(validation.errors) == 3  # SPF, DKIM, DMARC
    
    @patch.object(DNSValidator, "validate_domain")
    def test_validate_multiple_domains(self, mock_validate, validator):
        """Test validating multiple domains."""
        mock_validate.return_value = DNSValidation(domain="example.com")
        
        results = validator.validate_multiple_domains(
            domains=["example.com", "test.com"],
        )
        
        assert len(results) == 2
        assert mock_validate.call_count == 2
