"""
Timezone management utilities.

Provides cross-platform timezone detection and configuration.
"""

import subprocess
import platform
from typing import Optional, Dict
from pathlib import Path

from tools.core.logger import get_logger
from tools.core.exceptions import ToolsException

logger = get_logger(__name__)


class TimezoneError(ToolsException):
    """Raised when timezone operations fail."""
    pass


class TimezoneManager:
    """Manage system timezone configuration."""

    def __init__(self):
        """Initialize timezone manager."""
        self.platform = platform.system()
        logger.debug(f"Initialized TimezoneManager for platform: {self.platform}")

    def get_current_timezone(self) -> str:
        """
        Get current system timezone.

        Returns:
            str: Current timezone string (e.g., 'America/Mexico_City')

        Raises:
            TimezoneError: If timezone cannot be determined
        """
        try:
            if self.platform == "Linux":
                return self._get_timezone_linux()
            elif self.platform == "Windows":
                return self._get_timezone_windows()
            elif self.platform == "Darwin":
                return self._get_timezone_macos()
            else:
                raise TimezoneError(f"Unsupported platform: {self.platform}")
        except Exception as e:
            logger.error(f"Failed to get timezone: {e}")
            raise TimezoneError(f"Could not determine timezone: {e}")

    def _get_timezone_linux(self) -> str:
        """Get timezone on Linux using timedatectl."""
        try:
            result = subprocess.run(
                ["timedatectl"],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.split('\n'):
                if 'Time zone:' in line:
                    # Format: "Time zone: America/Mexico_City (CST, -0600)"
                    timezone = line.split(':')[1].strip().split()[0]
                    return timezone
            
            # Fallback: read /etc/timezone
            timezone_file = Path("/etc/timezone")
            if timezone_file.exists():
                return timezone_file.read_text().strip()
                
            raise TimezoneError("Could not parse timedatectl output")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"timedatectl failed: {e}")
            # Try alternative method
            if Path("/etc/localtime").is_symlink():
                link = Path("/etc/localtime").resolve()
                # /usr/share/zoneinfo/America/Mexico_City -> America/Mexico_City
                parts = str(link).split('/zoneinfo/')
                if len(parts) == 2:
                    return parts[1]
            raise TimezoneError("Could not determine Linux timezone")

    def _get_timezone_windows(self) -> str:
        """Get timezone on Windows."""
        try:
            result = subprocess.run(
                ["tzutil", "/g"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise TimezoneError(f"Failed to get Windows timezone: {e}")

    def _get_timezone_macos(self) -> str:
        """Get timezone on macOS."""
        try:
            result = subprocess.run(
                ["systemsetup", "-gettimezone"],
                capture_output=True,
                text=True,
                check=True
            )
            # Output: "Time Zone: America/Mexico_City"
            return result.stdout.split(':')[1].strip()
        except subprocess.CalledProcessError as e:
            raise TimezoneError(f"Failed to get macOS timezone: {e}")

    def set_timezone(self, timezone: str, sudo: bool = True) -> bool:
        """
        Set system timezone.

        Args:
            timezone: Timezone string (e.g., 'America/Mexico_City')
            sudo: Whether to use sudo (Linux only)

        Returns:
            bool: True if successful

        Raises:
            TimezoneError: If timezone cannot be set
        """
        logger.info(f"Setting timezone to: {timezone}")
        
        try:
            if self.platform == "Linux":
                return self._set_timezone_linux(timezone, sudo)
            elif self.platform == "Windows":
                return self._set_timezone_windows(timezone)
            elif self.platform == "Darwin":
                return self._set_timezone_macos(timezone, sudo)
            else:
                raise TimezoneError(f"Unsupported platform: {self.platform}")
        except Exception as e:
            logger.error(f"Failed to set timezone: {e}")
            raise TimezoneError(f"Could not set timezone: {e}")

    def _set_timezone_linux(self, timezone: str, sudo: bool) -> bool:
        """Set timezone on Linux using timedatectl."""
        cmd = ["timedatectl", "set-timezone", timezone]
        if sudo:
            cmd = ["sudo"] + cmd
            
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Successfully set timezone to: {timezone}")
            return True
        except subprocess.CalledProcessError as e:
            raise TimezoneError(f"Failed to set Linux timezone: {e.stderr.decode()}")

    def _set_timezone_windows(self, timezone: str) -> bool:
        """Set timezone on Windows."""
        try:
            subprocess.run(
                ["tzutil", "/s", timezone],
                check=True,
                capture_output=True
            )
            logger.info(f"Successfully set timezone to: {timezone}")
            return True
        except subprocess.CalledProcessError as e:
            raise TimezoneError(f"Failed to set Windows timezone: {e.stderr.decode()}")

    def _set_timezone_macos(self, timezone: str, sudo: bool) -> bool:
        """Set timezone on macOS."""
        cmd = ["systemsetup", "-settimezone", timezone]
        if sudo:
            cmd = ["sudo"] + cmd
            
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Successfully set timezone to: {timezone}")
            return True
        except subprocess.CalledProcessError as e:
            raise TimezoneError(f"Failed to set macOS timezone: {e.stderr.decode()}")

    def get_timezone_info(self) -> Dict[str, str]:
        """
        Get detailed timezone information.

        Returns:
            dict: Timezone details including current timezone, offset, etc.
        """
        info = {
            "platform": self.platform,
            "timezone": self.get_current_timezone()
        }
        
        if self.platform == "Linux":
            try:
                result = subprocess.run(
                    ["timedatectl"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                info["raw_output"] = result.stdout
            except subprocess.CalledProcessError:
                pass
                
        return info

    def list_available_timezones(self) -> list:
        """
        List available timezones on the system.

        Returns:
            list: Available timezone names
        """
        if self.platform == "Linux":
            zoneinfo = Path("/usr/share/zoneinfo")
            if zoneinfo.exists():
                # Get all timezone files
                zones = []
                for path in zoneinfo.rglob("*"):
                    if path.is_file() and not path.name.isupper():
                        relative = path.relative_to(zoneinfo)
                        # Skip posix, right directories
                        if not str(relative).startswith(("posix/", "right/")):
                            zones.append(str(relative))
                return sorted(zones)
        
        # For other platforms, return common zones
        return [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "America/Mexico_City",
            "Europe/London",
            "Europe/Paris",
            "Asia/Tokyo",
            "UTC"
        ]
