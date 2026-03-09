"""Fix missing or incorrect NS records in PowerDNS zones."""

import shlex
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from tools.core.logger import get_logger


class NSFixMode(str, Enum):
    """NS fix strategy."""

    ENFORCE = "enforce"
    APPEND = "append"


@dataclass
class NSFixResult:
    """Result of NS fix operation for one zone."""

    zone: str
    changed: bool = False
    status: str = "unchanged"
    current_ns: List[str] = field(default_factory=list)
    desired_ns: List[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "zone": self.zone,
            "changed": self.changed,
            "status": self.status,
            "current_ns": self.current_ns,
            "desired_ns": self.desired_ns,
            "error": self.error,
        }


class DNSNSFixer:
    """Ensures expected NS records in PowerDNS zones."""

    def __init__(
        self,
        ns1: str,
        ns2: str,
        ttl: int = 3600,
        mode: NSFixMode = NSFixMode.ENFORCE,
        pdnsutil_cmd: str = "pdnsutil",
        pdns_control_cmd: str = "pdns_control",
        command_timeout: int = 12,
    ):
        self.ns1 = self._normalize_fqdn(ns1)
        self.ns2 = self._normalize_fqdn(ns2)
        self.ttl = ttl
        self.mode = mode
        self.pdnsutil_cmd = pdnsutil_cmd
        self.pdns_control_cmd = pdns_control_cmd
        self.command_timeout = command_timeout
        self.logger = get_logger("dns.ns_fixer")

    def _normalize_fqdn(self, value: str) -> str:
        """Normalize FQDN with trailing dot."""
        cleaned = value.strip()
        if not cleaned.endswith("."):
            cleaned += "."
        return cleaned

    def _run_command(self, cmd: List[str], timeout: int = 0) -> str:
        """Run command and return stdout on success."""
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

    def _sort_unique(self, values: List[str]) -> List[str]:
        """Sort and deduplicate values."""
        return sorted(set(values))

    def _desired_ns(self) -> List[str]:
        """Expected NS records."""
        return self._sort_unique([self.ns1, self.ns2])

    def list_zones(self) -> List[str]:
        """List all zones via pdnsutil list-all-zones."""
        cmd = shlex.split(self.pdnsutil_cmd) + ["list-all-zones"]
        output = self._run_command(cmd)
        if not output:
            return []

        zones: List[str] = []
        for line in output.splitlines():
            zone = line.strip()
            if zone and zone not in zones:
                zones.append(zone)
        return zones

    def get_zone_ns(self, zone: str) -> List[str]:
        """Get current apex NS records from pdnsutil list-zone output."""
        cmd = shlex.split(self.pdnsutil_cmd) + ["list-zone", zone]
        output = self._run_command(cmd)
        if not output:
            return []

        records: List[str] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "NS":
                records.append(self._normalize_fqdn(parts[2]))

        return self._sort_unique(records)

    def _notify_zone(self, zone: str) -> None:
        """Send notify for zone when pdns_control is available."""
        cmd = shlex.split(self.pdns_control_cmd) + ["notify", zone]
        self._run_command(cmd)

    def _enforce_zone(self, zone: str, desired: List[str]) -> bool:
        """Replace NS rrset with exact desired values."""
        cmd_replace = (
            shlex.split(self.pdnsutil_cmd)
            + ["replace-rrset", zone, "@", "NS", str(self.ttl)]
            + desired
        )
        ok_replace = bool(self._run_command(cmd_replace))

        cmd_serial = shlex.split(self.pdnsutil_cmd) + ["increase-serial", zone]
        ok_serial = bool(self._run_command(cmd_serial))

        cmd_rectify = shlex.split(self.pdnsutil_cmd) + ["rectify-zone", zone]
        self._run_command(cmd_rectify)
        self._notify_zone(zone)

        return ok_replace and ok_serial

    def _append_zone(self, zone: str, current: List[str], desired: List[str]) -> bool:
        """Append missing desired NS values, keep existing ones."""
        missing = [ns for ns in desired if ns not in current]

        for ns in missing:
            cmd_add = shlex.split(self.pdnsutil_cmd) + ["add-record", zone, "@", "NS", ns]
            self._run_command(cmd_add)

        cmd_serial = shlex.split(self.pdnsutil_cmd) + ["increase-serial", zone]
        ok_serial = bool(self._run_command(cmd_serial))

        cmd_rectify = shlex.split(self.pdnsutil_cmd) + ["rectify-zone", zone]
        self._run_command(cmd_rectify)
        self._notify_zone(zone)

        return ok_serial

    def fix_zone(self, zone: str) -> NSFixResult:
        """Fix NS records for one zone according to selected mode."""
        desired = self._desired_ns()
        current = self.get_zone_ns(zone)

        result = NSFixResult(zone=zone, current_ns=current, desired_ns=desired)

        if self.mode == NSFixMode.ENFORCE:
            if current == desired:
                result.status = "unchanged"
                return result

            success = self._enforce_zone(zone, desired)
            result.changed = success
            result.status = "changed" if success else "failed"
            if not success:
                result.error = "Failed to replace NS rrset"
            return result

        # APPEND mode
        missing = [ns for ns in desired if ns not in current]
        if not missing:
            result.status = "unchanged"
            return result

        success = self._append_zone(zone, current, desired)
        result.changed = success
        result.status = "changed" if success else "failed"
        if not success:
            result.error = "Failed to append missing NS records"
        return result

    def fix_all_zones(self, zones: List[str] = None) -> List[NSFixResult]:
        """Fix NS for all zones or selected subset."""
        zone_list = zones if zones is not None else self.list_zones()
        return [self.fix_zone(zone) for zone in zone_list]

    def get_summary(self, results: List[NSFixResult]) -> Dict[str, Any]:
        """Build fix summary."""
        return {
            "total": len(results),
            "changed": sum(1 for r in results if r.status == "changed"),
            "unchanged": sum(1 for r in results if r.status == "unchanged"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "mode": self.mode.value,
        }
