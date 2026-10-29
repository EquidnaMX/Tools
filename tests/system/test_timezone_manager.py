"""
Tests for TimezoneManager.
"""

import pytest
from unittest.mock import Mock, patch
import subprocess

from tools.system.timezone_manager import TimezoneManager, TimezoneError


class TestTimezoneManager:
    """Test TimezoneManager functionality."""

    def test_init(self):
        """Test TimezoneManager initialization."""
        manager = TimezoneManager()
        assert manager.platform in ["Linux", "Windows", "Darwin"]

    @patch('platform.system')
    @patch('subprocess.run')
    def test_get_timezone_linux(self, mock_run, mock_platform):
        """Test getting timezone on Linux."""
        mock_platform.return_value = "Linux"
        mock_run.return_value = Mock(
            stdout="Time zone: America/Mexico_City (CST, -0600)\n",
            returncode=0
        )
        
        manager = TimezoneManager()
        tz = manager.get_current_timezone()
        
        assert tz == "America/Mexico_City"
        mock_run.assert_called_once()

    @patch('platform.system')
    @patch('subprocess.run')
    def test_get_timezone_windows(self, mock_run, mock_platform):
        """Test getting timezone on Windows."""
        mock_platform.return_value = "Windows"
        mock_run.return_value = Mock(
            stdout="Central Standard Time\n",
            returncode=0
        )
        
        manager = TimezoneManager()
        tz = manager.get_current_timezone()
        
        assert tz == "Central Standard Time"

    @patch('platform.system')
    @patch('subprocess.run')
    def test_get_timezone_macos(self, mock_run, mock_platform):
        """Test getting timezone on macOS."""
        mock_platform.return_value = "Darwin"
        mock_run.return_value = Mock(
            stdout="Time Zone: America/New_York\n",
            returncode=0
        )
        
        manager = TimezoneManager()
        tz = manager.get_current_timezone()
        
        assert tz == "America/New_York"

    @patch('platform.system')
    @patch('subprocess.run')
    def test_get_timezone_error(self, mock_run, mock_platform, monkeypatch):
        """Test error handling when getting timezone."""
        mock_platform.return_value = "Linux"
        mock_run.side_effect = subprocess.CalledProcessError(1, "timedatectl")
        # Do not consult the real host's /etc/localtime fallback.
        monkeypatch.setattr("tools.system.timezone_manager.Path.is_symlink", lambda _: False)
        
        manager = TimezoneManager()
        
        with pytest.raises(TimezoneError):
            manager.get_current_timezone()

    @pytest.mark.parametrize(
        "target,expected",
        [("/usr/share/zoneinfo/America/Mexico_City", "America/Mexico_City"),
         ("/tmp/unrelated", None)],
    )
    def test_timedatectl_failure_uses_only_controlled_fallback(self, target, expected):
        from pathlib import PurePosixPath

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "timedatectl")), \
             patch("tools.system.timezone_manager.Path") as path:
            path.return_value.is_symlink.return_value = True
            path.return_value.resolve.return_value = PurePosixPath(target)
            manager = TimezoneManager()
            if expected is None:
                with pytest.raises(TimezoneError):
                    manager.get_current_timezone()
            else:
                assert manager.get_current_timezone() == expected

    @patch('platform.system')
    def test_get_timezone_unsupported_platform(self, mock_platform):
        """Test unsupported platform."""
        mock_platform.return_value = "Unknown"
        
        manager = TimezoneManager()
        
        with pytest.raises(TimezoneError, match="Unsupported platform"):
            manager.get_current_timezone()

    @patch('platform.system')
    @patch('subprocess.run')
    def test_set_timezone_linux(self, mock_run, mock_platform):
        """Test setting timezone on Linux."""
        mock_platform.return_value = "Linux"
        mock_run.return_value = Mock(returncode=0)
        
        manager = TimezoneManager()
        result = manager.set_timezone("UTC", sudo=True)
        
        assert result is True
        mock_run.assert_called_once()
        # Verify sudo was used
        assert "sudo" in mock_run.call_args[0][0]

    @patch('platform.system')
    @patch('subprocess.run')
    def test_set_timezone_without_sudo(self, mock_run, mock_platform):
        """Test setting timezone without sudo."""
        mock_platform.return_value = "Linux"
        mock_run.return_value = Mock(returncode=0)
        
        manager = TimezoneManager()
        result = manager.set_timezone("UTC", sudo=False)
        
        assert result is True
        # Verify sudo was NOT used
        assert "sudo" not in mock_run.call_args[0][0]

    @patch('platform.system')
    @patch('subprocess.run')
    def test_set_timezone_error(self, mock_run, mock_platform):
        """Test error handling when setting timezone."""
        mock_platform.return_value = "Linux"
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "timedatectl", stderr=b"Invalid timezone"
        )
        
        manager = TimezoneManager()
        
        with pytest.raises(TimezoneError):
            manager.set_timezone("InvalidTZ")

    @patch('platform.system')
    @patch('subprocess.run')
    def test_get_timezone_info(self, mock_run, mock_platform):
        """Test getting detailed timezone info."""
        mock_platform.return_value = "Linux"
        mock_run.return_value = Mock(
            stdout="Time zone: UTC (UTC, +0000)\n",
            returncode=0
        )
        
        manager = TimezoneManager()
        info = manager.get_timezone_info()
        
        assert "platform" in info
        assert "timezone" in info
        assert info["platform"] == "Linux"

    @patch('platform.system')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.rglob')
    def test_list_available_timezones_linux(self, mock_rglob, mock_exists, mock_platform):
        """Test listing available timezones on Linux."""
        mock_platform.return_value = "Linux"
        mock_exists.return_value = True
        
        # Mock some timezone files
        mock_files = [
            Mock(is_file=lambda: True, name="New_York", relative_to=lambda x: "America/New_York"),
            Mock(is_file=lambda: True, name="London", relative_to=lambda x: "Europe/London"),
        ]
        mock_rglob.return_value = mock_files
        
        manager = TimezoneManager()
        zones = manager.list_available_timezones()
        
        assert isinstance(zones, list)
        # Should return some zones
        assert len(zones) >= 0

    @patch('platform.system')
    def test_list_available_timezones_non_linux(self, mock_platform):
        """Test listing timezones on non-Linux platforms."""
        mock_platform.return_value = "Windows"
        
        manager = TimezoneManager()
        zones = manager.list_available_timezones()
        
        # Should return common timezones
        assert isinstance(zones, list)
        assert "UTC" in zones
        assert "America/New_York" in zones
