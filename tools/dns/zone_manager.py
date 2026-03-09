"""DNS zone manager helpers."""

from dataclasses import dataclass
from typing import Any, Dict, List

from tools.dns.replication_checker import DNSReplicationChecker


@dataclass
class ZoneSOAInfo:
    """SOA info for one zone on both master and slave."""

    zone: str
    master_serial: str
    slave_serial: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "zone": self.zone,
            "master_serial": self.master_serial,
            "slave_serial": self.slave_serial,
        }


class DNSZoneManager:
    """Convenience wrapper for basic zone inspection operations."""

    def __init__(self, checker: DNSReplicationChecker):
        self.checker = checker

    def list_zones(self) -> List[str]:
        """List zones from PowerDNS."""
        return self.checker.get_zones_from_pdns()

    def get_soa_info(self, zone: str) -> ZoneSOAInfo:
        """Get master/slave SOA serial info for zone."""
        return ZoneSOAInfo(
            zone=zone,
            master_serial=self.checker.soa_serial(self.checker.master_ip, zone),
            slave_serial=self.checker.soa_serial(self.checker.slave_ip, zone),
        )
