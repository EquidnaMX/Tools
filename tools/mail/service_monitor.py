"""Service monitoring for mail server components.

This module provides functionality to monitor and check status of mail
server services like Postfix, Dovecot, Amavis, ClamAV, SpamAssassin, etc.
"""

import subprocess
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

from tools.core.logger import get_logger


class ServiceState(str, Enum):
    """Service state enumeration."""
    
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class ServiceStatus:
    """Status of a single service.
    
    Attributes:
        name: Service name
        state: Current state (active/inactive/failed/unknown)
        enabled: Whether service is enabled at boot
        pid: Process ID if running
        memory_usage: Memory usage in MB
        description: Service description
    """
    
    name: str
    state: ServiceState = ServiceState.UNKNOWN
    enabled: bool = False
    pid: Optional[int] = None
    memory_usage: Optional[float] = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with service status data
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "enabled": self.enabled,
            "pid": self.pid,
            "memory_mb": self.memory_usage,
            "description": self.description,
        }
    
    @property
    def is_running(self) -> bool:
        """Check if service is running.
        
        Returns:
            True if service is active
        """
        return self.state == ServiceState.ACTIVE


class ServiceMonitor:
    """Monitor for mail server services.
    
    Provides functionality to check status of mail server components
    using systemctl and other system utilities.
    """
    
    # Standard mail server services
    CORE_SERVICES = [
        "postfix",
        "dovecot",
    ]
    
    ANTISPAM_SERVICES = [
        "amavis",
        "clamav-daemon",
        "spamassassin",
    ]
    
    SECURITY_SERVICES = [
        "opendkim",
        "fail2ban",
    ]
    
    MAILING_LIST_SERVICES = [
        "sympa",
        "wwsympa",
    ]
    
    ALL_SERVICES = (
        CORE_SERVICES
        + ANTISPAM_SERVICES
        + SECURITY_SERVICES
        + MAILING_LIST_SERVICES
    )
    
    def __init__(self, timeout: int = 5):
        """Initialize service monitor.
        
        Args:
            timeout: Command timeout in seconds
        """
        self.timeout = timeout
        self.logger = get_logger("mail.service_monitor")
    
    def _run_command(
        self,
        cmd: List[str],
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a system command.
        
        Args:
            cmd: Command and arguments
            check: Raise exception on non-zero exit
            
        Returns:
            CompletedProcess instance
        """
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=check,
            )
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Command timeout: {' '.join(cmd)}")
            raise
        except FileNotFoundError:
            self.logger.error(f"Command not found: {cmd[0]}")
            raise
    
    def _check_systemctl_available(self) -> bool:
        """Check if systemctl is available.
        
        Returns:
            True if systemctl is available
        """
        try:
            result = self._run_command(["systemctl", "--version"])
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def check_service(self, service_name: str) -> ServiceStatus:
        """Check status of a single service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            ServiceStatus object
        """
        status = ServiceStatus(name=service_name)
        
        if not self._check_systemctl_available():
            self.logger.error("systemctl not available")
            return status
        
        # Check if service is active
        result = self._run_command(
            ["systemctl", "is-active", service_name],
            check=False,
        )
        
        state_output = result.stdout.strip()
        if state_output == "active":
            status.state = ServiceState.ACTIVE
        elif state_output == "inactive":
            status.state = ServiceState.INACTIVE
        elif state_output == "failed":
            status.state = ServiceState.FAILED
        else:
            status.state = ServiceState.UNKNOWN
        
        # Check if service is enabled
        result = self._run_command(
            ["systemctl", "is-enabled", service_name],
            check=False,
        )
        status.enabled = result.stdout.strip() == "enabled"
        
        # Get detailed status
        result = self._run_command(
            [
                "systemctl",
                "show",
                service_name,
                "--property=MainPID,MemoryCurrent,Description",
            ],
            check=False,
        )
        
        for line in result.stdout.split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                if key == "MainPID":
                    try:
                        pid = int(value)
                        if pid > 0:
                            status.pid = pid
                    except ValueError:
                        pass
                elif key == "MemoryCurrent":
                    try:
                        # Convert bytes to MB
                        bytes_mem = int(value)
                        if bytes_mem > 0:
                            status.memory_usage = bytes_mem / (1024 * 1024)
                    except ValueError:
                        pass
                elif key == "Description":
                    status.description = value
        
        self.logger.debug(
            f"Service {service_name}: {status.state.value} "
            f"(enabled: {status.enabled})"
        )
        
        return status
    
    def check_all_services(
        self,
        include_optional: bool = True,
    ) -> Dict[str, ServiceStatus]:
        """Check status of all mail server services.
        
        Args:
            include_optional: Include optional services (sympa, etc.)
            
        Returns:
            Dictionary mapping service name to ServiceStatus
        """
        services = self.CORE_SERVICES + self.ANTISPAM_SERVICES + self.SECURITY_SERVICES
        
        if include_optional:
            services = services + self.MAILING_LIST_SERVICES
        
        results = {}
        
        for service in services:
            status = self.check_service(service)
            results[service] = status
        
        # Log summary
        active_count = sum(1 for s in results.values() if s.is_running)
        self.logger.info(
            f"Service check complete: {active_count}/{len(results)} services active"
        )
        
        return results
    
    def get_service_summary(
        self,
        services: Optional[Dict[str, ServiceStatus]] = None,
    ) -> Dict[str, str]:
        """Get simple summary of service states.
        
        Args:
            services: Service status dict (checks all if not provided)
            
        Returns:
            Dictionary mapping service name to state string
        """
        if services is None:
            services = self.check_all_services()
        
        return {
            name: status.state.value
            for name, status in services.items()
        }
    
    def check_apache_sympa_config(self) -> Dict[str, Any]:
        """Check Apache configuration for Sympa.
        
        Returns:
            Dictionary with Apache/Sympa configuration status
        """
        result = {
            "conf_enabled": False,
            "modules_ok": False,
            "modules_found": [],
        }
        
        # Check if sympa.conf is enabled
        try:
            conf_path = "/etc/apache2/conf-enabled/sympa.conf"
            import os
            result["conf_enabled"] = os.path.exists(conf_path)
        except Exception as exc:
            self.logger.debug(f"Could not check Apache config: {exc}")
        
        # Check Apache modules
        try:
            cmd_result = self._run_command(["apache2ctl", "-M"], check=False)
            
            if cmd_result.returncode == 0:
                modules_output = cmd_result.stdout
                
                # Required modules for Sympa
                required_modules = [
                    "cgi_module",
                    "mpm_event_module",
                    "proxy_fcgi_module",
                    "fcgid_module",
                ]
                
                found_modules = []
                for module in required_modules:
                    if module in modules_output:
                        found_modules.append(module)
                
                result["modules_found"] = found_modules
                result["modules_ok"] = len(found_modules) > 0
                
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            self.logger.debug(f"Could not check Apache modules: {exc}")
        
        return result
    
    def get_failed_services(
        self,
        services: Optional[Dict[str, ServiceStatus]] = None,
    ) -> List[str]:
        """Get list of failed services.
        
        Args:
            services: Service status dict (checks all if not provided)
            
        Returns:
            List of failed service names
        """
        if services is None:
            services = self.check_all_services()
        
        return [
            name for name, status in services.items()
            if status.state == ServiceState.FAILED
        ]
    
    def get_inactive_services(
        self,
        services: Optional[Dict[str, ServiceStatus]] = None,
    ) -> List[str]:
        """Get list of inactive services.
        
        Args:
            services: Service status dict (checks all if not provided)
            
        Returns:
            List of inactive service names
        """
        if services is None:
            services = self.check_all_services()
        
        return [
            name for name, status in services.items()
            if status.state == ServiceState.INACTIVE
        ]
