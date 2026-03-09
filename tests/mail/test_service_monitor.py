"""Tests for ServiceMonitor module."""

import pytest
from unittest.mock import patch, MagicMock

from tools.mail.service_monitor import ServiceMonitor, ServiceStatus, ServiceState


class TestServiceStatus:
    """Test ServiceStatus dataclass."""
    
    def test_service_status_initialization(self):
        """Test ServiceStatus initialization."""
        status = ServiceStatus(name="postfix")
        
        assert status.name == "postfix"
        assert status.state == ServiceState.UNKNOWN
        assert status.enabled is False
        assert status.pid is None
        assert status.memory_usage is None
    
    def test_service_status_is_running(self):
        """Test is_running property."""
        status_active = ServiceStatus(name="postfix", state=ServiceState.ACTIVE)
        status_inactive = ServiceStatus(name="dovecot", state=ServiceState.INACTIVE)
        
        assert status_active.is_running is True
        assert status_inactive.is_running is False
    
    def test_service_status_to_dict(self):
        """Test ServiceStatus to_dict method."""
        status = ServiceStatus(
            name="postfix",
            state=ServiceState.ACTIVE,
            enabled=True,
            pid=1234,
            memory_usage=50.5,
            description="Mail Transfer Agent",
        )
        
        result = status.to_dict()
        
        assert result["name"] == "postfix"
        assert result["state"] == "active"
        assert result["enabled"] is True
        assert result["pid"] == 1234
        assert result["memory_mb"] == 50.5
        assert result["description"] == "Mail Transfer Agent"


class TestServiceMonitor:
    """Test ServiceMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create ServiceMonitor instance for testing."""
        return ServiceMonitor(timeout=3)
    
    def test_monitor_initialization(self, monitor):
        """Test ServiceMonitor initialization."""
        assert monitor.timeout == 3
        assert "postfix" in monitor.CORE_SERVICES
        assert "amavis" in monitor.ANTISPAM_SERVICES
        assert "opendkim" in monitor.SECURITY_SERVICES
        assert "sympa" in monitor.MAILING_LIST_SERVICES
    
    @patch("subprocess.run")
    def test_check_systemctl_available(self, mock_run, monitor):
        """Test systemctl availability check."""
        mock_run.return_value = MagicMock(returncode=0)
        
        available = monitor._check_systemctl_available()
        
        assert available is True
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "systemctl" in call_args
        assert "--version" in call_args
    
    @patch("subprocess.run")
    def test_check_systemctl_not_available(self, mock_run, monitor):
        """Test systemctl not available."""
        mock_run.side_effect = FileNotFoundError()
        
        available = monitor._check_systemctl_available()
        
        assert available is False
    
    @patch("subprocess.run")
    def test_check_service_active(self, mock_run, monitor):
        """Test checking an active service."""
        # Mock responses for different systemctl commands
        def run_side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return MagicMock(returncode=0, stdout="active\n")
            elif "is-enabled" in cmd:
                return MagicMock(returncode=0, stdout="enabled\n")
            elif "show" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="MainPID=1234\nMemoryCurrent=52428800\nDescription=Mail Transfer Agent\n"
                )
            else:
                return MagicMock(returncode=0, stdout="")
        
        mock_run.side_effect = run_side_effect
        
        status = monitor.check_service("postfix")
        
        assert status.name == "postfix"
        assert status.state == ServiceState.ACTIVE
        assert status.enabled is True
        assert status.pid == 1234
        assert status.memory_usage == 50.0  # 52428800 bytes / (1024*1024) ≈ 50 MB
        assert "Mail Transfer Agent" in status.description
    
    @patch("subprocess.run")
    def test_check_service_inactive(self, mock_run, monitor):
        """Test checking an inactive service."""
        def run_side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return MagicMock(returncode=3, stdout="inactive\n")
            elif "is-enabled" in cmd:
                return MagicMock(returncode=0, stdout="disabled\n")
            elif "show" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="MainPID=0\nMemoryCurrent=0\nDescription=Service\n"
                )
            else:
                return MagicMock(returncode=0, stdout="")
        
        mock_run.side_effect = run_side_effect
        
        status = monitor.check_service("dovecot")
        
        assert status.state == ServiceState.INACTIVE
        assert status.enabled is False
        assert status.pid is None
    
    @patch("subprocess.run")
    def test_check_service_failed(self, mock_run, monitor):
        """Test checking a failed service."""
        def run_side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return MagicMock(returncode=3, stdout="failed\n")
            else:
                return MagicMock(returncode=0, stdout="")
        
        mock_run.side_effect = run_side_effect
        
        status = monitor.check_service("amavis")
        
        assert status.state == ServiceState.FAILED
    
    @patch("subprocess.run")
    def test_check_service_systemctl_not_available(self, mock_run, monitor):
        """Test checking service when systemctl not available."""
        mock_run.side_effect = FileNotFoundError()
        
        status = monitor.check_service("postfix")
        
        assert status.name == "postfix"
        assert status.state == ServiceState.UNKNOWN
    
    @patch.object(ServiceMonitor, "check_service")
    def test_check_all_services(self, mock_check_service, monitor):
        """Test checking all services."""
        # Mock check_service to return active for postfix, inactive for others
        def check_side_effect(name):
            if name == "postfix":
                return ServiceStatus(name=name, state=ServiceState.ACTIVE)
            else:
                return ServiceStatus(name=name, state=ServiceState.INACTIVE)
        
        mock_check_service.side_effect = check_side_effect
        
        results = monitor.check_all_services(include_optional=False)
        
        # Check that we got results for core + antispam + security services
        expected_count = (
            len(monitor.CORE_SERVICES) +
            len(monitor.ANTISPAM_SERVICES) +
            len(monitor.SECURITY_SERVICES)
        )
        assert len(results) == expected_count
        assert "postfix" in results
        assert results["postfix"].state == ServiceState.ACTIVE
    
    @patch.object(ServiceMonitor, "check_service")
    def test_check_all_services_with_optional(self, mock_check_service, monitor):
        """Test checking all services including optional."""
        mock_check_service.return_value = ServiceStatus(
            name="test", state=ServiceState.ACTIVE
        )
        
        results = monitor.check_all_services(include_optional=True)
        
        # Should include mailing list services
        expected_count = (
            len(monitor.CORE_SERVICES) +
            len(monitor.ANTISPAM_SERVICES) +
            len(monitor.SECURITY_SERVICES) +
            len(monitor.MAILING_LIST_SERVICES)
        )
        assert len(results) == expected_count
    
    def test_get_service_summary(self, monitor):
        """Test get_service_summary method."""
        services = {
            "postfix": ServiceStatus(name="postfix", state=ServiceState.ACTIVE),
            "dovecot": ServiceStatus(name="dovecot", state=ServiceState.INACTIVE),
            "amavis": ServiceStatus(name="amavis", state=ServiceState.FAILED),
        }
        
        summary = monitor.get_service_summary(services)
        
        assert summary["postfix"] == "active"
        assert summary["dovecot"] == "inactive"
        assert summary["amavis"] == "failed"
    
    @patch("subprocess.run")
    def test_check_apache_sympa_config(self, mock_run, monitor):
        """Test checking Apache Sympa configuration."""
        # Mock apache2ctl -M output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="cgi_module (shared)\nmpm_event_module (shared)\n"
        )
        
        with patch("os.path.exists", return_value=True):
            result = monitor.check_apache_sympa_config()
        
        assert result["conf_enabled"] is True
        assert result["modules_ok"] is True
        assert "cgi_module" in result["modules_found"]
        assert "mpm_event_module" in result["modules_found"]
    
    @patch("subprocess.run")
    def test_check_apache_sympa_config_missing(self, mock_run, monitor):
        """Test checking Apache Sympa config when missing."""
        mock_run.side_effect = FileNotFoundError()
        
        result = monitor.check_apache_sympa_config()
        
        assert result["conf_enabled"] is False
        assert result["modules_ok"] is False
    
    def test_get_failed_services(self, monitor):
        """Test getting list of failed services."""
        services = {
            "postfix": ServiceStatus(name="postfix", state=ServiceState.ACTIVE),
            "dovecot": ServiceStatus(name="dovecot", state=ServiceState.INACTIVE),
            "amavis": ServiceStatus(name="amavis", state=ServiceState.FAILED),
            "clamav": ServiceStatus(name="clamav", state=ServiceState.FAILED),
        }
        
        failed = monitor.get_failed_services(services)
        
        assert len(failed) == 2
        assert "amavis" in failed
        assert "clamav" in failed
        assert "postfix" not in failed
    
    def test_get_inactive_services(self, monitor):
        """Test getting list of inactive services."""
        services = {
            "postfix": ServiceStatus(name="postfix", state=ServiceState.ACTIVE),
            "dovecot": ServiceStatus(name="dovecot", state=ServiceState.INACTIVE),
            "sympa": ServiceStatus(name="sympa", state=ServiceState.INACTIVE),
        }
        
        inactive = monitor.get_inactive_services(services)
        
        assert len(inactive) == 2
        assert "dovecot" in inactive
        assert "sympa" in inactive
        assert "postfix" not in inactive
