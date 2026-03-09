"""Mail server auditor - comprehensive mail server audit functionality.

This module provides the main MailAuditor class that coordinates domain
discovery, service monitoring, DNS validation, and reputation checks to
generate comprehensive mail server audit reports.
"""

import subprocess
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from tools.core.logger import get_logger
from tools.mail.dns_validator import DNSValidator, DNSValidation
from tools.mail.service_monitor import ServiceMonitor, ServiceStatus


@dataclass
class ReputationCheck:
    """RBL (Real-time Blackhole List) reputation check result.
    
    Attributes:
        rbl_name: Name of the RBL service
        listed: Whether the IP is listed
        response: Response from RBL (IP if listed)
    """
    
    rbl_name: str
    listed: bool = False
    response: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "rbl": self.rbl_name,
            "status": "listed" if self.listed else "clean",
            "response": self.response,
        }


@dataclass
class DomainAuditResult:
    """Audit result for a single domain.
    
    Attributes:
        domain: Domain name
        dns_validation: DNS validation results
        sympa_robot: Sympa robot configuration status
        sympa_aliases: Sympa aliases status
    """
    
    domain: str
    dns_validation: Optional[DNSValidation] = None
    sympa_robot: str = "not_configured"
    sympa_aliases: str = "missing"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        result: Dict[str, Any] = {
            "domain": self.domain,
        }
        
        if self.dns_validation:
            result["records"] = self.dns_validation.to_dict()["records"]
        
        result["sympa"] = {
            "robot": self.sympa_robot,
            "aliases_in_etc_aliases": self.sympa_aliases,
        }
        
        return result


@dataclass
class AuditReport:
    """Complete mail server audit report.
    
    Attributes:
        timestamp: Audit timestamp
        server_ip: Server IP address
        server_hostname: Server hostname
        ptr_record: PTR record for server IP
        ptr_target: Expected PTR value
        ptr_status: PTR validation status
        services: Service status dictionary
        apache_sympa: Apache/Sympa configuration
        domains: List of domain audit results
        reputation: List of RBL check results
        discovered_domains: Set of discovered domain names
        errors: List of errors encountered
    """
    
    timestamp: datetime = field(default_factory=datetime.now)
    server_ip: str = ""
    server_hostname: str = ""
    ptr_record: str = ""
    ptr_target: str = ""
    ptr_status: str = "unknown"
    services: Dict[str, ServiceStatus] = field(default_factory=dict)
    apache_sympa: Dict[str, Any] = field(default_factory=dict)
    domains: List[DomainAuditResult] = field(default_factory=list)
    reputation: List[ReputationCheck] = field(default_factory=list)
    discovered_domains: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export.
        
        Returns:
            Dictionary representation
        """
        # Build service summary
        service_summary = {
            name: status.state.value
            for name, status in self.services.items()
        }
        service_summary.update(self.apache_sympa)
        
        return {
            "timestamp": self.timestamp.isoformat(),
            "server": {
                "ip": self.server_ip,
                "hostname": self.server_hostname,
                "ptr_current": self.ptr_record,
                "ptr_target": self.ptr_target,
                "ptr_status": self.ptr_status,
                "services": service_summary,
            },
            "domains": [d.to_dict() for d in self.domains],
            "reputation": {
                r.rbl_name: "listed" if r.listed else "clean"
                for r in self.reputation
            },
            "summary": {
                "total_domains": len(self.domains),
                "services_active": sum(
                    1 for s in self.services.values() if s.is_running
                ),
                "services_total": len(self.services),
                "blacklists_listed": sum(1 for r in self.reputation if r.listed),
            },
            "errors": self.errors,
        }


class MailAuditor:
    """Mail server auditor.
    
    Performs comprehensive mail server audits including:
    - Domain discovery from Postfix, OpenDKIM, Sympa
    - Service status monitoring
    - DNS record validation (MX, SPF, DKIM, DMARC, PTR)
    - RBL reputation checks
    - Sympa configuration validation
    """
    
    # Default domains to always include
    DEFAULT_DOMAINS = []
    
    # Standard RBL services
    DEFAULT_RBLS = [
        "zen.spamhaus.org",
        "b.barracudacentral.org",
        "bl.spamcop.net",
    ]
    
    def __init__(
        self,
        ptr_target: Optional[str] = None,
        dkim_selector: str = "default",
        timeout: int = 5,
        include_rbls: bool = True,
    ):
        """Initialize mail auditor.
        
        Args:
            ptr_target: Expected PTR record value
            dkim_selector: DKIM selector to use
            timeout: Command timeout in seconds
            include_rbls: Include RBL reputation checks
        """
        self.ptr_target = ptr_target
        self.dkim_selector = dkim_selector
        self.timeout = timeout
        self.include_rbls = include_rbls
        self.logger = get_logger("mail.auditor")
        
        self.dns_validator = DNSValidator(
            timeout=timeout,
            dkim_selector=dkim_selector,
        )
        self.service_monitor = ServiceMonitor(timeout=timeout)
    
    def _run_command(self, cmd: List[str]) -> str:
        """Run command and return output.
        
        Args:
            cmd: Command and arguments
            
        Returns:
            Command output
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
            self.logger.debug(f"Command failed {' '.join(cmd)}: {exc}")
            return ""
    
    def get_server_ip(self) -> str:
        """Get primary server IP address.
        
        Returns:
            IP address as string
        """
        try:
            # Try hostname -I first
            result = self._run_command(["hostname", "-I"])
            if result:
                # Return first IP
                return result.split()[0]
            
            # Fallback: use socket
            hostname = socket.gethostname()
            return socket.gethostbyname(hostname)
            
        except Exception as exc:
            self.logger.warning(f"Could not determine server IP: {exc}")
            return ""
    
    def get_server_hostname(self) -> str:
        """Get server hostname.
        
        Returns:
            Hostname as string
        """
        try:
            return socket.getfqdn()
        except Exception as exc:
            self.logger.warning(f"Could not determine hostname: {exc}")
            return ""
    
    def discover_domains_from_postfix(self) -> Set[str]:
        """Discover domains from Postfix configuration.
        
        Returns:
            Set of domain names
        """
        domains: Set[str] = set()
        
        # Postfix configuration keys to check
        config_keys = [
            "mydestination",
            "virtual_mailbox_domains",
            "relay_domains",
        ]
        
        for key in config_keys:
            output = self._run_command(["postconf", "-h", key])
            
            if output:
                # Split by comma and whitespace
                for value in re.split(r'[,\s]+', output):
                    value = value.strip()
                    # Validate domain format
                    if re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', value):
                        domains.add(value)
                        self.logger.debug(f"Found domain in Postfix {key}: {value}")
        
        return domains
    
    def discover_domains_from_opendkim(self) -> Set[str]:
        """Discover domains from OpenDKIM configuration.
        
        Returns:
            Set of domain names
        """
        domains: Set[str] = set()
        
        # Check signing.table
        signing_table = Path("/etc/opendkim/signing.table")
        
        if signing_table.exists():
            try:
                content = signing_table.read_text()
                
                for line in content.split("\n"):
                    # Skip comments and empty lines
                    if line.strip().startswith("#") or not line.strip():
                        continue
                    
                    # Format: pattern selector._domainkey.domain
                    # Extract domain from second field
                    parts = line.split()
                    if len(parts) >= 2:
                        # Extract domain from selector._domainkey.domain
                        match = re.search(r'_domainkey\.([A-Za-z0-9.-]+)', parts[1])
                        if match:
                            domain = match.group(1)
                            domains.add(domain)
                            self.logger.debug(f"Found domain in OpenDKIM: {domain}")
                
            except Exception as exc:
                self.logger.debug(f"Could not read signing.table: {exc}")
        
        return domains
    
    def discover_domains_from_sympa(self) -> Set[str]:
        """Discover domains from Sympa configuration.
        
        Returns:
            Set of domain names
        """
        domains: Set[str] = set()
        
        # Check new layout: /etc/sympa/domains/
        domains_dir = Path("/etc/sympa/domains")
        
        if domains_dir.exists() and domains_dir.is_dir():
            try:
                for item in domains_dir.iterdir():
                    if item.is_dir():
                        domain = item.name
                        if re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', domain):
                            domains.add(domain)
                            self.logger.debug(f"Found domain in Sympa (new): {domain}")
            except Exception as exc:
                self.logger.debug(f"Could not read Sympa domains dir: {exc}")
        
        # Check legacy layout: /etc/sympa/*/robot.conf
        sympa_dir = Path("/etc/sympa")
        
        if sympa_dir.exists():
            try:
                for robot_conf in sympa_dir.glob("*/robot.conf"):
                    domain = robot_conf.parent.name
                    if re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', domain):
                        domains.add(domain)
                        self.logger.debug(f"Found domain in Sympa (legacy): {domain}")
            except Exception as exc:
                self.logger.debug(f"Could not read Sympa legacy configs: {exc}")
        
        return domains
    
    def discover_all_domains(
        self,
        additional_domains: Optional[List[str]] = None,
    ) -> List[str]:
        """Discover all mail domains.
        
        Args:
            additional_domains: Additional domains to include
            
        Returns:
            Sorted list of unique domain names
        """
        self.logger.info("Discovering mail domains...")
        
        all_domains: Set[str] = set()
        
        # Discover from various sources
        all_domains.update(self.discover_domains_from_postfix())
        all_domains.update(self.discover_domains_from_opendkim())
        all_domains.update(self.discover_domains_from_sympa())
        
        # Add default domains
        all_domains.update(self.DEFAULT_DOMAINS)
        
        # Add additional domains
        if additional_domains:
            all_domains.update(additional_domains)
        
        domains_list = sorted(all_domains)
        
        self.logger.info(f"Discovered {len(domains_list)} domains: {', '.join(domains_list)}")
        
        return domains_list
    
    def check_sympa_robot(self, domain: str) -> str:
        """Check if Sympa robot is configured for domain.
        
        Args:
            domain: Domain name
            
        Returns:
            "configured" or "not_configured"
        """
        # Check new layout
        robot_conf = Path(f"/etc/sympa/domains/{domain}/robot.conf")
        if robot_conf.exists():
            return "configured"
        
        # Check legacy layout
        robot_conf = Path(f"/etc/sympa/{domain}/robot.conf")
        if robot_conf.exists():
            return "configured"
        
        return "not_configured"
    
    def check_sympa_aliases(self) -> str:
        """Check if Sympa aliases are present in /etc/aliases.
        
        Returns:
            "present" or "missing"
        """
        aliases_file = Path("/etc/aliases")
        
        if not aliases_file.exists():
            return "missing"
        
        try:
            content = aliases_file.read_text()
            
            # Look for sympa: alias
            if re.search(r'(^|\s)sympa:', content):
                return "present"
            
        except Exception as exc:
            self.logger.debug(f"Could not read /etc/aliases: {exc}")
        
        return "missing"
    
    def check_ip_reputation(self, ip: str) -> List[ReputationCheck]:
        """Check IP reputation against RBLs.
        
        Args:
            ip: IP address to check
            
        Returns:
            List of ReputationCheck results
        """
        if not self.include_rbls:
            return []
        
        self.logger.info(f"Checking IP reputation for {ip}")
        
        # Reverse IP for RBL queries
        octets = ip.split(".")
        if len(octets) != 4:
            self.logger.warning(f"Invalid IP format: {ip}")
            return []
        
        reversed_ip = ".".join(reversed(octets))
        
        results = []
        
        for rbl in self.DEFAULT_RBLS:
            check = ReputationCheck(rbl_name=rbl)
            
            query = f"{reversed_ip}.{rbl}"
            response = self.dns_validator._dig_query(query, "A")
            
            if response:
                # IP is listed
                check.listed = True
                check.response = response
                self.logger.warning(f"IP {ip} is listed on {rbl}: {response}")
            else:
                check.listed = False
                self.logger.debug(f"IP {ip} is clean on {rbl}")
            
            results.append(check)
        
        return results
    
    def audit_domain(self, domain: str, server_ip: str) -> DomainAuditResult:
        """Audit a single domain.
        
        Args:
            domain: Domain name
            server_ip: Server IP for PTR validation
            
        Returns:
            DomainAuditResult object
        """
        result = DomainAuditResult(domain=domain)
        
        # DNS validation
        result.dns_validation = self.dns_validator.validate_domain(
            domain=domain,
            selector=self.dkim_selector,
            expected_ptr=self.ptr_target,
            server_ip=server_ip,
        )
        
        # Sympa checks
        result.sympa_robot = self.check_sympa_robot(domain)
        result.sympa_aliases = self.check_sympa_aliases()
        
        return result
    
    def audit_server(
        self,
        domains: Optional[List[str]] = None,
    ) -> AuditReport:
        """Perform complete server audit.
        
        Args:
            domains: Specific domains to audit (auto-discovers if None)
            
        Returns:
            AuditReport object
        """
        self.logger.info("Starting mail server audit...")
        
        report = AuditReport()
        
        # Server information
        report.server_ip = self.get_server_ip()
        report.server_hostname = self.get_server_hostname()
        report.ptr_target = self.ptr_target or ""
        
        if report.server_ip:
            report.ptr_record = self.dns_validator.get_ptr_record(report.server_ip)
            
            if report.ptr_target:
                ptr_match = (
                    report.ptr_record == report.ptr_target or
                    report.ptr_record == f"{report.ptr_target}."
                )
                report.ptr_status = "ok" if ptr_match else "mismatch"
            else:
                report.ptr_status = "not_checked"
        
        # Service status
        try:
            report.services = self.service_monitor.check_all_services()
            report.apache_sympa = self.service_monitor.check_apache_sympa_config()
        except Exception as exc:
            error_msg = f"Service check failed: {exc}"
            self.logger.error(error_msg)
            report.errors.append(error_msg)
        
        # Discover or use provided domains
        if domains is None:
            domains = self.discover_all_domains()
        
        report.discovered_domains = set(domains)
        
        # Audit each domain
        for domain in domains:
            try:
                domain_result = self.audit_domain(domain, report.server_ip)
                report.domains.append(domain_result)
            except Exception as exc:
                error_msg = f"Domain audit failed for {domain}: {exc}"
                self.logger.error(error_msg)
                report.errors.append(error_msg)
        
        # Reputation checks
        if report.server_ip and self.include_rbls:
            try:
                report.reputation = self.check_ip_reputation(report.server_ip)
            except Exception as exc:
                error_msg = f"Reputation check failed: {exc}"
                self.logger.error(error_msg)
                report.errors.append(error_msg)
        
        self.logger.info(
            f"Audit complete: {len(report.domains)} domains, "
            f"{sum(1 for s in report.services.values() if s.is_running)} services active"
        )
        
        return report
