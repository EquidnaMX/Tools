"""DNS replication checker for PowerDNS master and BIND slave setups."""

import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from tools.core.logger import get_logger


class ReplicationStatus(str, Enum):
    """Replication comparison status."""

    OK = "ok"
    DESYNC = "desync"
    ERROR_MASTER = "error_master"
    ERROR_SLAVE = "error_slave"


@dataclass
class SerialComparison:
    """SOA serial comparison result for one zone."""

    zone: str
    master_serial: str = ""
    slave_serial: str = ""
    status: ReplicationStatus = ReplicationStatus.ERROR_MASTER
    master_soa: str = ""
    slave_soa: str = ""
    retransfer_attempted: bool = False
    retransfer_success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert comparison result to dictionary."""
        return {
            "zone": self.zone,
            "master_serial": self.master_serial,
            "slave_serial": self.slave_serial,
            "status": self.status.value,
            "master_soa": self.master_soa,
            "slave_soa": self.slave_soa,
            "retransfer_attempted": self.retransfer_attempted,
            "retransfer_success": self.retransfer_success,
        }


class DNSReplicationChecker:
    """Checks DNS zone serial replication between master and slave."""

    def __init__(
        self,
        master_ip: str,
        slave_ip: str,
        pdns_control_cmd: str = "pdns_control",
        dig_timeout: int = 3,
        dig_tries: int = 1,
        ssh_slave: Optional[str] = None,
        retry_retransfer: bool = True,
        command_timeout: int = 8,
    ):
        self.master_ip = master_ip
        self.slave_ip = slave_ip
        self.pdns_control_cmd = pdns_control_cmd
        self.dig_timeout = dig_timeout
        self.dig_tries = dig_tries
        self.ssh_slave = ssh_slave
        self.retry_retransfer = retry_retransfer
        self.command_timeout = command_timeout
        self.logger = get_logger("dns.replication")

    def _run_command(self, cmd: List[str], timeout: Optional[int] = None) -> str:
        """Run subprocess command and return stdout on success."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.command_timeout,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
            self.logger.debug("Command failed %s: %s", " ".join(cmd), exc)
            return ""

    def get_zones_from_pdns(self) -> List[str]:
        """Get zones from PowerDNS using pdns_control list-zones."""
        cmd = shlex.split(self.pdns_control_cmd) + ["list-zones"]
        output = self._run_command(cmd)
        if not output:
            return []

        zones: List[str] = []
        for raw in output.splitlines():
            zone = raw.strip()
            if not zone:
                continue
            if zone.endswith("."):
                zone = zone[:-1]
            if zone and zone not in zones:
                zones.append(zone)
        return zones

    def soa_raw(self, server: str, zone: str) -> str:
        """Get raw SOA response for a server/zone."""
        cmd = [
            "dig",
            f"+time={self.dig_timeout}",
            f"+tries={self.dig_tries}",
            f"@{server}",
            zone,
            "SOA",
            "+short",
        ]
        return self._run_command(cmd, timeout=self.dig_timeout + 2)

    def soa_serial(self, server: str, zone: str) -> str:
        """Extract SOA serial from dig +short SOA output."""
        raw = self.soa_raw(server, zone)
        if not raw:
            return ""

        first_line = raw.splitlines()[0].strip()
        parts = first_line.split()
        if len(parts) < 3:
            return ""
        return parts[2]

    def validate_axfr(self, server: str, zone: str) -> bool:
        """Validate whether AXFR appears to succeed for a zone."""
        cmd = [
            "dig",
            f"+time={self.dig_timeout}",
            f"+tries={self.dig_tries}",
            f"@{server}",
            zone,
            "AXFR",
            "+noall",
            "+answer",
        ]
        output = self._run_command(cmd, timeout=self.dig_timeout + 2)
        if not output:
            return False

        upper = output.upper()
        return (
            "XFR SIZE" in upper
            or "\tIN\t" in output
            or " IN " in output
        )

    def compare_serials(
        self,
        zone: str,
        master: Optional[str] = None,
        slave: Optional[str] = None,
    ) -> SerialComparison:
        """Compare SOA serial for zone between master and slave."""
        master_host = master or self.master_ip
        slave_host = slave or self.slave_ip

        comparison = SerialComparison(zone=zone)
        comparison.master_soa = self.soa_raw(master_host, zone)
        comparison.slave_soa = self.soa_raw(slave_host, zone)

        comparison.master_serial = self.soa_serial(master_host, zone)
        comparison.slave_serial = self.soa_serial(slave_host, zone)

        if not comparison.master_serial:
            comparison.status = ReplicationStatus.ERROR_MASTER
        elif not comparison.slave_serial:
            comparison.status = ReplicationStatus.ERROR_SLAVE
        elif comparison.master_serial == comparison.slave_serial:
            comparison.status = ReplicationStatus.OK
        else:
            comparison.status = ReplicationStatus.DESYNC

        return comparison

    def trigger_retransfer(self, zone: str, slave_host: Optional[str] = None) -> bool:
        """Trigger rndc retransfer using SSH to slave host."""
        host = slave_host or self.ssh_slave
        if not host:
            return False

        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=4",
            host,
            f"sudo rndc retransfer {zone} ; sudo rndc zonestatus {zone}",
        ]
        output = self._run_command(cmd, timeout=15)
        return bool(output)

    def check_replication(
        self,
        zones: Optional[List[str]] = None,
        auto_retransfer: Optional[bool] = None,
    ) -> List[SerialComparison]:
        """Check replication for all or provided zones."""
        zone_list = zones if zones is not None else self.get_zones_from_pdns()
        results: List[SerialComparison] = []

        do_retransfer = self.retry_retransfer if auto_retransfer is None else auto_retransfer

        for zone in zone_list:
            result = self.compare_serials(zone)

            if result.status == ReplicationStatus.DESYNC and do_retransfer and self.ssh_slave:
                result.retransfer_attempted = True
                result.retransfer_success = self.trigger_retransfer(zone)

                if result.retransfer_success:
                    post = self.compare_serials(zone)
                    result.slave_serial = post.slave_serial
                    result.slave_soa = post.slave_soa
                    result.status = post.status

            results.append(result)

        return results

    def get_summary(self, results: List[SerialComparison]) -> Dict[str, Any]:
        """Build summary stats for replication results."""
        return {
            "total_zones": len(results),
            "ok": sum(1 for r in results if r.status == ReplicationStatus.OK),
            "desync": sum(1 for r in results if r.status == ReplicationStatus.DESYNC),
            "error_master": sum(1 for r in results if r.status == ReplicationStatus.ERROR_MASTER),
            "error_slave": sum(1 for r in results if r.status == ReplicationStatus.ERROR_SLAVE),
            "retransfer_attempted": sum(1 for r in results if r.retransfer_attempted),
            "retransfer_success": sum(1 for r in results if r.retransfer_success),
        }
