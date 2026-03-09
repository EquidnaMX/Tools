"""Domain health checker for mail domains.

This module provides quick health checks for mail domains, including
DNS validation, connectivity tests, and OpenDKIM selector parsing.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from tools.core.logger import get_logger
from tools.mail.dns_validator import DNSValidator


@dataclass
class ConnectivityCheck:
    """SMTP connectivity check result.
    
    Attributes:
        host: Hostname checked
        port: Port number
        reachable: Whether host is reachable
        response_time: Response time in ms
    """
    
    host: str
    port: int = 25
    reachable: bool = False
    response_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "host": self.host,
            "port": self.port,
            "reachable": self.reachable,
            "response_time_ms": self.response_time,
        }


@dataclass
class DomainHealth:
    """Health check result for a domain.
    
    Attributes:
        domain: Domain name
        selector: DKIM selector
        has_mx: Has MX records
        has_spf: Has SPF record
        has_dkim: Has DKIM record
        has_dmarc: Has DMARC record
        mx_reachable: MX servers reachable
        mx_hosts: List of MX hostnames
        connectivity: List of connectivity checks
        score: Health score (0-100)
        issues: List of issues found
    """
    
    domain: str
    selector: str = "default"
    has_mx: bool = False
    has_spf: bool = False
    has_dkim: bool = False
    has_dmarc: bool = False
    mx_reachable: bool = False
    mx_hosts: List[str] = field(default_factory=list)
    connectivity: List[ConnectivityCheck] = field(default_factory=list)
    score: int = 0
    issues: List[str] = field(default_factory=list)
    
    def calculate_score(self) -> int:
        """Calculate health score based on checks.
        
        Returns:
            Score from 0 to 100
        """
        score = 0
        
        # MX records (required)
        if self.has_mx:
            score += 25
        else:
            self.issues.append("Missing MX records")
        
        # SPF (important)
        if self.has_spf:
            score += 25
        else:
            self.issues.append("Missing SPF record")
        
        # DKIM (important)
        if self.has_dkim:
            score += 20
        else:
            self.issues.append("Missing DKIM record")
        
        # DMARC (recommended)
        if self.has_dmarc:
            score += 15
        else:
            self.issues.append("Missing DMARC record")
        
        # Connectivity (critical)
        if self.mx_reachable:
            score += 15
        else:
            self.issues.append("MX servers not reachable")
        
        self.score = score
        return score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "domain": self.domain,
            "selector": self.selector,
            "checks": {
                "has_mx": self.has_mx,
                "has_spf": self.has_spf,
                "has_dkim": self.has_dkim,
                "has_dmarc": self.has_dmarc,
                "mx_reachable": self.mx_reachable,
            },
            "mx_hosts": self.mx_hosts,
            "connectivity": [c.to_dict() for c in self.connectivity],
            "score": self.score,
            "issues": self.issues,
        }


class DomainHealthChecker:
    """Health checker for mail domains.
    
    Provides quick health checks for mail domains including DNS validation
    and SMTP connectivity tests.
    """
    
    def __init__(
        self,
        timeout: int = 4,
        check_connectivity: bool = True,
    ):
        """Initialize domain health checker.
        
        Args:
            timeout: Timeout for checks in seconds
            check_connectivity: Check SMTP connectivity
        """
        self.timeout = timeout
        self.check_connectivity = check_connectivity
        self.logger = get_logger("mail.domain_health")
        
        self.dns_validator = DNSValidator(timeout=timeout)
    
    def parse_opendkim_signing_table(
        self,
        signing_table_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        """Parse OpenDKIM signing table to get domain selectors.
        
        Args:
            signing_table_path: Path to signing.table file
            
        Returns:
            Dictionary mapping domain to selector
        """
        selectors = {}
        
        # Try to get path from postconf
        if signing_table_path is None:
            try:
                result = subprocess.run(
                    ["postconf", "-h", "SigningTable"],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                
                if result.returncode == 0:
                    conf_value = result.stdout.strip()
                    
                    # Handle different formats: refile:/path, file:/path, /path
                    if conf_value.startswith("refile:") or conf_value.startswith("file:"):
                        signing_table_path = Path(conf_value.split(":", 1)[1])
                    elif conf_value.startswith("/"):
                        signing_table_path = Path(conf_value)
                    
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        
        # Default path
        if signing_table_path is None:
            signing_table_path = Path("/etc/opendkim/signing.table")
        
        if not signing_table_path.exists():
            self.logger.debug(f"Signing table not found: {signing_table_path}")
            return selectors
        
        try:
            content = signing_table_path.read_text()
            
            for line in content.split("\n"):
                # Skip comments and empty lines
                if line.strip().startswith("#") or not line.strip():
                    continue
                
                # Format: pattern selector._domainkey.domain
                parts = line.split()
                if len(parts) >= 2:
                    # Extract selector and domain
                    match = re.match(
                        r'([^._]+)\._domainkey\.([A-Za-z0-9.-]+)',
                        parts[1]
                    )
                    if match:
                        selector = match.group(1)
                        domain = match.group(2)
                        selectors[domain] = selector
                        self.logger.debug(
                            f"Found selector '{selector}' for domain '{domain}'"
                        )
            
        except Exception as exc:
            self.logger.debug(f"Could not parse signing table: {exc}")
        
        return selectors
    
    def parse_opendkim_key_table(
        self,
        key_table_path: Path = Path("/etc/opendkim/key.table"),
    ) -> Dict[str, str]:
        """Parse OpenDKIM key table to get domain selectors.
        
        Args:
            key_table_path: Path to key.table file
            
        Returns:
            Dictionary mapping domain to selector
        """
        selectors = {}
        
        if not key_table_path.exists():
            self.logger.debug(f"Key table not found: {key_table_path}")
            return selectors
        
        try:
            content = key_table_path.read_text()
            
            for line in content.split("\n"):
                # Skip comments and empty lines
                if line.strip().startswith("#") or not line.strip():
                    continue
                
                # Format: selector._domainkey.domain domain:selector:/path/to/key
                parts = line.split()
                if len(parts) >= 1:
                    # Extract selector and domain from first field
                    match = re.match(
                        r'([^._]+)\._domainkey\.([A-Za-z0-9.-]+)',
                        parts[0]
                    )
                    if match:
                        selector = match.group(1)
                        domain = match.group(2)
                        selectors[domain] = selector
                        self.logger.debug(
                            f"Found selector '{selector}' for domain '{domain}' in key table"
                        )
            
        except Exception as exc:
            self.logger.debug(f"Could not parse key table: {exc}")
        
        return selectors
    
    def get_domain_selector(
        self,
        domain: str,
        selectors: Optional[Dict[str, str]] = None,
    ) -> str:
        """Get DKIM selector for domain.
        
        Args:
            domain: Domain name
            selectors: Pre-parsed selectors dict
            
        Returns:
            Selector name (defaults to "default")
        """
        if selectors is None:
            selectors = self.parse_opendkim_signing_table()
            
            if not selectors:
                selectors = self.parse_opendkim_key_table()
        
        return selectors.get(domain, "default")
    
    def check_smtp_connectivity(self, host: str, port: int = 25) -> ConnectivityCheck:
        """Check SMTP connectivity to a host.
        
        Args:
            host: Hostname
            port: Port number
            
        Returns:
            ConnectivityCheck result
        """
        check = ConnectivityCheck(host=host, port=port)
        
        try:
            import time
            start_time = time.time()
            
            # Use nc (netcat) if available
            result = subprocess.run(
                ["nc", "-z", "-w", str(self.timeout), host, str(port)],
                capture_output=True,
                timeout=self.timeout + 1,
                check=False,
            )
            
            if result.returncode == 0:
                check.reachable = True
                check.response_time = (time.time() - start_time) * 1000
            
        except FileNotFoundError:
            # nc not available, try telnet or socket
            try:
                import socket
                import time
                
                start_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    check.reachable = True
                    check.response_time = (time.time() - start_time) * 1000
                
            except Exception as exc:
                self.logger.debug(f"Connectivity check failed for {host}:{port}: {exc}")
        
        except Exception as exc:
            self.logger.debug(f"Connectivity check failed for {host}:{port}: {exc}")
        
        return check
    
    def check_domain_health(
        self,
        domain: str,
        selector: Optional[str] = None,
    ) -> DomainHealth:
        """Check health of a domain.
        
        Args:
            domain: Domain name
            selector: DKIM selector (auto-detects if not provided)
            
        Returns:
            DomainHealth object
        """
        self.logger.info(f"Checking health for domain: {domain}")
        
        # Get selector
        if selector is None:
            selector = self.get_domain_selector(domain)
        
        health = DomainHealth(domain=domain, selector=selector)
        
        # MX records
        mx_records = self.dns_validator.get_mx_records(domain)
        health.has_mx = len(mx_records) > 0
        
        if health.has_mx:
            # Extract just the hostnames
            health.mx_hosts = [
                mx.split()[1] for mx in mx_records if len(mx.split()) >= 2
            ]
        
        # SPF
        spf = self.dns_validator.get_spf_record(domain)
        health.has_spf = bool(spf)
        
        # DKIM
        dkim = self.dns_validator.get_dkim_record(domain, selector)
        health.has_dkim = bool(dkim)
        
        # DMARC
        dmarc = self.dns_validator.get_dmarc_record(domain)
        health.has_dmarc = bool(dmarc)
        
        # Connectivity checks
        if self.check_connectivity and health.mx_hosts:
            for mx_host in health.mx_hosts:
                connectivity = self.check_smtp_connectivity(mx_host, 25)
                health.connectivity.append(connectivity)
                
                if connectivity.reachable:
                    health.mx_reachable = True
        
        # Calculate score
        health.calculate_score()
        
        self.logger.info(
            f"Domain {domain} health score: {health.score}/100 "
            f"({len(health.issues)} issues)"
        )
        
        return health
    
    def check_multiple_domains(
        self,
        domains: List[str],
        selectors: Optional[Dict[str, str]] = None,
    ) -> List[DomainHealth]:
        """Check health of multiple domains.
        
        Args:
            domains: List of domain names
            selectors: Dictionary mapping domain to selector
            
        Returns:
            List of DomainHealth objects
        """
        results = []
        
        # Parse selectors once if not provided
        if selectors is None:
            selectors = self.parse_opendkim_signing_table()
            if not selectors:
                selectors = self.parse_opendkim_key_table()
        
        for domain in domains:
            selector = selectors.get(domain)
            health = self.check_domain_health(domain, selector)
            results.append(health)
        
        return results
    
    def get_summary(self, results: List[DomainHealth]) -> Dict[str, Any]:
        """Get summary of health check results.
        
        Args:
            results: List of DomainHealth objects
            
        Returns:
            Summary dictionary
        """
        total = len(results)
        
        if total == 0:
            return {
                "total_domains": 0,
                "healthy": 0,
                "warnings": 0,
                "critical": 0,
            }
        
        # Categorize by score
        healthy = sum(1 for r in results if r.score >= 80)
        warnings = sum(1 for r in results if 50 <= r.score < 80)
        critical = sum(1 for r in results if r.score < 50)
        
        avg_score = sum(r.score for r in results) / total
        
        return {
            "total_domains": total,
            "healthy": healthy,
            "warnings": warnings,
            "critical": critical,
            "average_score": round(avg_score, 1),
        }
