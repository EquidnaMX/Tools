"""DNS validation for mail domains.

This module provides DNS validation functionality for mail server domains,
including SPF, DKIM, DMARC, MX, and PTR record validation.
"""

import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from tools.core.logger import get_logger


@dataclass
class DNSValidation:
    """DNS validation results for a domain.
    
    Attributes:
        domain: Domain name
        mx_records: List of MX records
        a_record: A record for mail.domain
        spf_record: SPF record
        dkim_record: DKIM record
        dmarc_record: DMARC record
        ptr_record: PTR record
        has_mx: Whether domain has MX records
        has_spf: Whether domain has SPF record
        has_dkim: Whether domain has DKIM record
        has_dmarc: Whether domain has DMARC record
        ptr_matches: Whether PTR matches expected value
        errors: List of validation errors
    """
    
    domain: str
    mx_records: List[str] = field(default_factory=list)
    a_record: str = ""
    spf_record: str = ""
    dkim_record: str = ""
    dmarc_record: str = ""
    ptr_record: str = ""
    has_mx: bool = False
    has_spf: bool = False
    has_dkim: bool = False
    has_dmarc: bool = False
    ptr_matches: bool = False
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with all validation data
        """
        return {
            "domain": self.domain,
            "records": {
                "A_mail": self.a_record,
                "MX": "; ".join(self.mx_records),
                "SPF": self.spf_record,
                "DKIM": self.dkim_record,
                "DMARC": self.dmarc_record,
                "PTR": self.ptr_record,
            },
            "validation": {
                "has_mx": self.has_mx,
                "has_spf": self.has_spf,
                "has_dkim": self.has_dkim,
                "has_dmarc": self.has_dmarc,
                "ptr_matches": self.ptr_matches,
            },
            "errors": self.errors,
        }


class DNSValidator:
    """DNS validator for mail domains.
    
    Validates DNS records required for mail server operation including
    MX, SPF, DKIM, DMARC, A records and PTR records.
    """
    
    def __init__(
        self,
        timeout: int = 4,
        retries: int = 1,
        dkim_selector: str = "default",
    ):
        """Initialize DNS validator.
        
        Args:
            timeout: DNS query timeout in seconds
            retries: Number of retries for failed queries
            dkim_selector: Default DKIM selector to use
        """
        self.timeout = timeout
        self.retries = retries
        self.dkim_selector = dkim_selector
        self.logger = get_logger("mail.dns_validator")
    
    def _dig_query(
        self,
        query: str,
        record_type: str = "A",
        short: bool = True,
    ) -> str:
        """Execute dig query and return result.
        
        Args:
            query: DNS query string
            record_type: DNS record type
            short: Use short output format
            
        Returns:
            Query result as string
        """
        cmd = [
            "dig",
            f"+time={self.timeout}",
            f"+tries={self.retries}",
            "+nocmd",
            "+noall",
            "+answer",
        ]
        
        if short:
            cmd.append("+short")
        
        cmd.extend([query, record_type])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 2,
                check=False,
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                self.logger.debug(
                    f"dig query failed for {query} {record_type}: {result.stderr}"
                )
                return ""
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"DNS query timeout for {query} {record_type}")
            return ""
        except FileNotFoundError:
            self.logger.error("dig command not found - install dnsutils/bind-utils")
            return ""
        except Exception as exc:
            self.logger.error(f"DNS query error: {exc}")
            return ""
    
    def get_mx_records(self, domain: str) -> List[str]:
        """Get MX records for domain.
        
        Args:
            domain: Domain name
            
        Returns:
            List of MX records sorted by priority
        """
        result = self._dig_query(domain, "MX", short=False)
        
        if not result:
            return []
        
        mx_records = []
        for line in result.split("\n"):
            if line and not line.startswith(";"):
                parts = line.split()
                if len(parts) >= 5:
                    # Format: domain. TTL IN MX priority host.
                    priority = parts[4]
                    host = parts[5].rstrip(".")
                    mx_records.append(f"{priority} {host}")
        
        # Sort by priority (first field)
        mx_records.sort(key=lambda x: int(x.split()[0]))
        return mx_records
    
    def get_a_record(self, hostname: str) -> str:
        """Get A record for hostname.
        
        Args:
            hostname: Hostname to query
            
        Returns:
            IP address or empty string
        """
        result = self._dig_query(hostname, "A")
        # Return first IP if multiple
        return result.split("\n")[0] if result else ""
    
    def get_spf_record(self, domain: str) -> str:
        """Get SPF record for domain.
        
        Args:
            domain: Domain name
            
        Returns:
            SPF record or empty string
        """
        result = self._dig_query(domain, "TXT")
        
        # Find SPF record (starts with v=spf1)
        for line in result.split("\n"):
            line = line.strip().strip('"')
            if line.startswith("v=spf1"):
                return line
        
        return ""
    
    def get_dkim_record(
        self,
        domain: str,
        selector: Optional[str] = None,
    ) -> str:
        """Get DKIM record for domain.
        
        Args:
            domain: Domain name
            selector: DKIM selector (uses default if not provided)
            
        Returns:
            DKIM record or empty string
        """
        selector = selector or self.dkim_selector
        dkim_domain = f"{selector}._domainkey.{domain}"
        
        result = self._dig_query(dkim_domain, "TXT")
        
        # DKIM records can be split across multiple strings
        # Remove quotes and join
        if result:
            cleaned = result.replace('"', '').replace('\n', '')
            return cleaned
        
        return ""
    
    def get_dmarc_record(self, domain: str) -> str:
        """Get DMARC record for domain.
        
        Args:
            domain: Domain name
            
        Returns:
            DMARC record or empty string
        """
        dmarc_domain = f"_dmarc.{domain}"
        result = self._dig_query(dmarc_domain, "TXT")
        
        # Remove quotes
        if result:
            return result.strip('"')
        
        return ""
    
    def get_ptr_record(self, ip: str) -> str:
        """Get PTR record for IP address.
        
        Args:
            ip: IP address
            
        Returns:
            PTR record (hostname) or empty string
        """
        result = self._dig_query(ip, "PTR")
        
        # Remove trailing dot
        if result:
            return result.rstrip(".")
        
        return ""
    
    def validate_domain(
        self,
        domain: str,
        selector: Optional[str] = None,
        expected_ptr: Optional[str] = None,
        server_ip: Optional[str] = None,
    ) -> DNSValidation:
        """Validate all DNS records for a domain.
        
        Args:
            domain: Domain name to validate
            selector: DKIM selector (optional)
            expected_ptr: Expected PTR value (optional)
            server_ip: Server IP for PTR validation (optional)
            
        Returns:
            DNSValidation object with results
        """
        self.logger.info(f"Validating DNS for domain: {domain}")
        
        validation = DNSValidation(domain=domain)
        
        # MX records
        validation.mx_records = self.get_mx_records(domain)
        validation.has_mx = len(validation.mx_records) > 0
        if not validation.has_mx:
            validation.errors.append(f"No MX records found for {domain}")
        
        # A record for mail.domain
        validation.a_record = self.get_a_record(f"mail.{domain}")
        if not validation.a_record:
            self.logger.debug(f"No A record for mail.{domain}")
        
        # SPF
        validation.spf_record = self.get_spf_record(domain)
        validation.has_spf = bool(validation.spf_record)
        if not validation.has_spf:
            validation.errors.append(f"No SPF record found for {domain}")
        
        # DKIM
        validation.dkim_record = self.get_dkim_record(domain, selector)
        validation.has_dkim = bool(validation.dkim_record)
        if not validation.has_dkim:
            validation.errors.append(
                f"No DKIM record found for {domain} (selector: {selector or self.dkim_selector})"
            )
        
        # DMARC
        validation.dmarc_record = self.get_dmarc_record(domain)
        validation.has_dmarc = bool(validation.dmarc_record)
        if not validation.has_dmarc:
            validation.errors.append(f"No DMARC record found for {domain}")
        
        # PTR validation
        if server_ip and expected_ptr:
            validation.ptr_record = self.get_ptr_record(server_ip)
            validation.ptr_matches = (
                validation.ptr_record == expected_ptr or
                validation.ptr_record == f"{expected_ptr}."
            )
            if not validation.ptr_matches:
                validation.errors.append(
                    f"PTR mismatch: got '{validation.ptr_record}', expected '{expected_ptr}'"
                )
        
        if validation.errors:
            self.logger.warning(
                f"DNS validation for {domain} completed with {len(validation.errors)} errors"
            )
        else:
            self.logger.info(f"DNS validation for {domain} completed successfully")
        
        return validation
    
    def validate_multiple_domains(
        self,
        domains: List[str],
        selector: Optional[str] = None,
        expected_ptr: Optional[str] = None,
        server_ip: Optional[str] = None,
    ) -> List[DNSValidation]:
        """Validate DNS records for multiple domains.
        
        Args:
            domains: List of domain names
            selector: DKIM selector (optional)
            expected_ptr: Expected PTR value (optional)
            server_ip: Server IP for PTR validation (optional)
            
        Returns:
            List of DNSValidation objects
        """
        results = []
        
        for domain in domains:
            validation = self.validate_domain(
                domain=domain,
                selector=selector,
                expected_ptr=expected_ptr,
                server_ip=server_ip,
            )
            results.append(validation)
        
        return results
