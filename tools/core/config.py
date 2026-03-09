"""
Configuration management with YAML profiles.
Adapts cloud/config_manager.py for unified toolkit use.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .exceptions import ConfigError


class ConfigProfile:
    """Single configuration profile with sensible defaults."""

    def __init__(self, name: str, config_dict: Dict[str, Any]):
        """Initialize a configuration profile.

        Args:
            name: Profile name
            config_dict: Profile configuration dictionary

        Raises:
            ConfigError: If required fields are missing
        """
        self.name = name
        self.config = config_dict or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self.config.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary."""
        return {"name": self.name, **self.config}

    def to_cli_args(self) -> List[str]:
        """Convert profile to CLI arguments."""
        args = []
        for key, value in self.config.items():
            if isinstance(value, bool):
                if value:
                    args.append(f"--{key}")
            elif value is not None:
                args.append(f"--{key}")
                args.append(str(value))
        return args

    def __repr__(self) -> str:
        return f"ConfigProfile(name={self.name}, config={self.config})"


class ConfigManager:
    """Manage YAML configuration profiles with auto-discovery of config files."""

    def __init__(self, config_file: Optional[Path] = None):
        """Initialize configuration manager.

        Args:
            config_file: Optional explicit path to config file.
                        If None, searches standard locations.

        Raises:
            ConfigError: If config file is invalid YAML or missing required sections
        """
        self.config_file = config_file or self._find_config_file()
        self.profiles: Dict[str, ConfigProfile] = {}
        self.defaults: Dict[str, Any] = {}

        if self.config_file and self.config_file.exists():
            self.load_config(self.config_file)

    def _find_config_file(self) -> Optional[Path]:
        """Auto-discover config file from standard locations."""
        search_paths = [
            Path.cwd() / "profiles.yml",
            Path.cwd() / "config.yml",
            Path.home() / ".tools" / "profiles.yml",
            Path.home() / ".config" / "tools" / "profiles.yml",
            Path("/etc/tools/profiles.yml"),
        ]

        for path in search_paths:
            if path.exists():
                return path
        return None

    def load_config(self, config_file: Path) -> None:
        """Load YAML configuration file.

        Args:
            config_file: Path to YAML config file

        Raises:
            ConfigError: If file cannot be read or YAML is invalid
        """
        if not config_file.exists():
            raise ConfigError(f"Config file not found: {config_file}")

        try:
            with open(config_file, "r") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {config_file}: {e}")
        except IOError as e:
            raise ConfigError(f"Cannot read {config_file}: {e}")

        # Load default values
        self.defaults = data.get("defaults", {})

        # Load profiles
        profiles_data = data.get("profiles", {})
        for profile_name, profile_config in profiles_data.items():
            merged_config = {**self.defaults}
            merged_config.update(profile_config or {})
            self.profiles[profile_name] = ConfigProfile(
                profile_name, merged_config
            )

    def get_profile(self, name: str) -> ConfigProfile:
        """Get profile by name.

        Args:
            name: Profile name

        Raises:
            ConfigError: If profile not found

        Returns:
            ConfigProfile instance
        """
        if name not in self.profiles:
            available = ", ".join(self.profiles.keys())
            raise ConfigError(
                f"Profile '{name}' not found. Available: {available}"
            )
        return self.profiles[name]

    def list_profiles(self) -> List[str]:
        """List all available profile names."""
        return list(self.profiles.keys())

    def __repr__(self) -> str:
        return (
            f"ConfigManager(file={self.config_file},"
            f" profiles={list(self.profiles.keys())})"
        )
