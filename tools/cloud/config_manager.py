"""
YAML Configuration module for cloud storage sync.
Provides profile management and configuration loading.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging


class ConfigError(Exception):
    """Raised when configuration is invalid"""
    pass


class ConfigProfile:
    """Represents a single configuration profile"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize from profile name and config dict"""
        self.name = name
        self._config = config
        self._validate()
    
    def _validate(self):
        """Validate required fields"""
        required = ["region", "bucket", "dest"]
        for field in required:
            if field not in self._config:
                raise ConfigError(f"Profile '{self.name}' missing required field: {field}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CLI arguments"""
        return self._config.copy()
    
    def to_cli_args(self) -> List[str]:
        """Convert to CLI arguments"""
        args = []
        
        # Required fields
        args.extend(["--region", str(self.get("region"))])
        args.extend(["--bucket", str(self.get("bucket"))])
        args.extend(["--dest", str(self.get("dest"))])
        
        # Optional fields
        if self.get("prefix"):
            args.extend(["--prefix", str(self.get("prefix"))])
        
        if self.get("workers"):
            args.extend(["--workers", str(self.get("workers"))])
        
        if self.get("delete"):
            args.append("--delete")
        
        if self.get("dry_run"):
            args.append("--dry-run")
        
        if self.get("exclude"):
            for pattern in self.get("exclude", []):
                args.extend(["--exclude", pattern])
        
        if not self.get("show_progress", True):
            args.append("--no-progress")
        
        if self.get("log_level"):
            args.extend(["--log-level", self.get("log_level")])
        
        if self.get("output_json"):
            args.extend(["--output-json", str(self.get("output_json"))])
        
        if self.get("detailed_report"):
            args.append("--detailed-report")
        
        return args
    
    def __repr__(self):
        return f"ConfigProfile('{self.name}', region={self.get('region')}, bucket={self.get('bucket')})"


class ConfigManager:
    """Manages YAML configuration files and profiles"""
    
    # Standard configuration file locations
    CONFIG_PATHS = [
        Path.cwd() / "download_do_space_config.yml",  # Current directory
        Path.cwd() / ".tools" / "cloud_profiles.yml",  # Project .tools directory
        Path.home() / ".download_do_space" / "profiles.yml",  # User home (legacy)
        Path.home() / ".tools" / "cloud_profiles.yml",  # User home
        Path.home() / ".config" / "tools" / "cloud_profiles.yml",  # XDG config
        Path("/etc/tools/cloud_profiles.yml"),  # System-wide (Unix)
    ]
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize configuration manager"""
        self.logger = logger or logging.getLogger(__name__)
        self.profiles: Dict[str, ConfigProfile] = {}
        self._loaded_file = None
    
    def load_config(self, config_file: Optional[str] = None) -> bool:
        """
        Load configuration from YAML file
        
        Args:
            config_file: Specific config file to load. If None, searches standard paths
        
        Returns:
            True if config was loaded, False if no config found
        """
        file_to_load = None
        
        if config_file:
            # Use specified file
            file_path = Path(config_file).expanduser()
            if not file_path.exists():
                raise ConfigError(f"Configuration file not found: {file_path}")
            file_to_load = file_path
        else:
            # Search standard paths
            for path in self.CONFIG_PATHS:
                if path.exists():
                    file_to_load = path
                    break
        
        if not file_to_load:
            self.logger.debug("No configuration file found in standard paths")
            return False
        
        try:
            with open(file_to_load, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            
            self._loaded_file = file_to_load
            self.profiles.clear()
            
            for profile_name, profile_config in config_data.items():
                if not isinstance(profile_config, dict):
                    self.logger.warning(f"Skipping invalid profile '{profile_name}': not a dictionary")
                    continue
                
                try:
                    self.profiles[profile_name] = ConfigProfile(profile_name, profile_config)
                    self.logger.debug(f"Loaded profile: {profile_name}")
                except ConfigError as e:
                    self.logger.warning(f"Error loading profile '{profile_name}': {e}")
            
            self.logger.info(f"✓ Loaded {len(self.profiles)} profile(s) from {file_to_load}")
            return len(self.profiles) > 0
        
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {file_to_load}: {e}")
        except Exception as e:
            raise ConfigError(f"Error loading config from {file_to_load}: {e}")
    
    def get_profile(self, name: str) -> Optional[ConfigProfile]:
        """Get a profile by name"""
        return self.profiles.get(name)
    
    def list_profiles(self) -> List[str]:
        """List all available profile names"""
        return sorted(self.profiles.keys())
    
    def has_profile(self, name: str) -> bool:
        """Check if profile exists"""
        return name in self.profiles
    
    def get_loaded_file(self) -> Optional[Path]:
        """Get path of currently loaded configuration file"""
        return self._loaded_file
    
    def print_profiles(self):
        """Print all available profiles with descriptions"""
        if not self.profiles:
            print("No profiles configured")
            return
        
        print(f"\n📋 Available profiles (from {self._loaded_file}):\n")
        for name in self.list_profiles():
            profile = self.profiles[name]
            desc = profile.get("description", "No description")
            region = profile.get("region", "unknown")
            bucket = profile.get("bucket", "unknown")
            print(f"  • {name:20} - {desc}")
            print(f"    Region: {region}, Bucket: {bucket}\n")
