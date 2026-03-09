"""
Cloud provider factory for creating appropriate provider instances.
"""

import logging
from typing import Dict, Any, Optional

from tools.cloud.providers import CloudProvider
from tools.core.logger import get_logger


class CloudProviderFactory:
    """Factory for creating cloud provider instances."""
    
    # Load providers dynamically to handle optional dependencies
    _PROVIDERS_CACHE = None
    _ERRORS_CACHE = {}
    
    @classmethod
    def _load_providers(cls) -> Dict[str, Optional[Any]]:
        """Load provider classes dynamically, handling optional dependencies."""
        if cls._PROVIDERS_CACHE is not None:
            return cls._PROVIDERS_CACHE
        
        providers = {
            "aws": None,
            "s3": None,
            "aws-s3": None,
            "google": None,
            "gcs": None,
            "google-cloud": None,
            "google-cloud-storage": None,
            "azure": None,
            "azure-blob": None,
            "digitalocean": None,
            "do": None,
        }
        
        # Try to import AWS S3
        try:
            from tools.cloud.aws_s3 import S3Provider
            providers["aws"] = S3Provider
            providers["s3"] = S3Provider
            providers["aws-s3"] = S3Provider
        except ImportError as e:
            cls._ERRORS_CACHE["aws"] = str(e)
        
        # Try to import Google Cloud Storage
        try:
            from tools.cloud.google_cloud import GCSProvider
            providers["google"] = GCSProvider
            providers["gcs"] = GCSProvider
            providers["google-cloud"] = GCSProvider
            providers["google-cloud-storage"] = GCSProvider
        except ImportError as e:
            cls._ERRORS_CACHE["gcs"] = str(e)
        
        # Try to import Azure Blob Storage
        try:
            from tools.cloud.azure_blob import AzureBlobProvider
            providers["azure"] = AzureBlobProvider
            providers["azure-blob"] = AzureBlobProvider
        except ImportError as e:
            cls._ERRORS_CACHE["azure"] = str(e)
        
        cls._PROVIDERS_CACHE = providers
        return providers
    
    @property
    def SUPPORTED_PROVIDERS(self) -> Dict[str, Optional[Any]]:
        """Get supported providers mapping."""
        return self._load_providers()
    
    @classmethod
    def create(cls,
               provider_type: str,
               config: Dict[str, Any],
               logger: Optional[logging.Logger] = None) -> CloudProvider:
        """
        Create cloud provider instance.
        
        Args:
            provider_type: Provider type (aws, gcs, azure, etc.)
            config: Configuration dictionary
            logger: Logger instance
            
        Returns:
            CloudProvider instance
            
        Raises:
            ValueError: If provider type not supported or config invalid
        """
        logger = logger or get_logger(__name__)
        
        providers = cls._load_providers()
        provider_lower = provider_type.lower().strip()
        
        if provider_lower not in providers:
            available = ", ".join(sorted(p for p in providers.keys() if providers[p]))
            raise ValueError(
                f"Unknown provider: {provider_type}\n"
                f"Supported providers: {available}"
            )
        
        provider_class = providers[provider_lower]
        
        if provider_class is None:
            error_msg = cls._ERRORS_CACHE.get(provider_lower, "Unknown error")
            raise ValueError(
                f"Provider '{provider_type}' dependencies not installed:\n{error_msg}"
            )
        
        try:
            return provider_class(logger=logger, **config)
        except TypeError as e:
            raise ValueError(
                f"Invalid configuration for {provider_type}: {e}"
            )
    
    @classmethod
    def detect_provider_from_config(cls, config: Dict[str, Any]) -> str:
        """
        Detect provider type from configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Provider type string
            
        Raises:
            ValueError: If provider type cannot be detected
        """
        # Check explicit provider field
        if "provider" in config:
            return config["provider"]
        
        # Auto-detect based on endpoint/region
        if "endpoint_url" in config:
            endpoint = config["endpoint_url"].lower()
            if "digitaloceanspaces" in endpoint:
                return "digitalocean"
            elif "amazonaws" in endpoint or "s3" in endpoint:
                return "aws"
        
        if "region" in config:
            region = config["region"].lower()
            if "digitaloceanspaces" in region or region in ["sfo3", "nyc3", "sgp1", "ams3"]:
                return "digitalocean"
        
        if "project_id" in config or "google_cloud" in str(config).lower():
            return "gcs"
        
        if "account_name" in config or "container" in config:
            return "azure"
        
        raise ValueError(
            "Cannot auto-detect provider. Please specify 'provider' in configuration."
        )
    
    @classmethod
    def get_credential_requirements(cls, provider_type: str) -> Dict[str, str]:
        """
        Get credential requirements for a provider.
        
        Args:
            provider_type: Provider type
            
        Returns:
            Dictionary of environment variable requirements
        """
        providers = cls._load_providers()
        provider_lower = provider_type.lower().strip()
        
        if provider_lower not in providers:
            raise ValueError(f"Unknown provider: {provider_type}")
        
        provider_class = providers[provider_lower]
        
        if provider_class is None:
            return {}
        
        # Create dummy instance to get requirements
        try:
            # Create minimal config
            dummy_config = {
                "bucket": "dummy",
                "dest": "/tmp",
            }
            
            if provider_lower in ["aws", "s3", "aws-s3"]:
                dummy_config.update({
                    "region": "us-east-1",
                    "access_key": "dummy",
                    "secret_key": "dummy",
                })
            elif provider_lower in ["google", "gcs", "google-cloud", "google-cloud-storage"]:
                dummy_config.update({
                    "project_id": "dummy",
                    "credentials_path": "/tmp/dummy.json",
                })
            elif provider_lower in ["azure", "azure-blob"]:
                dummy_config.update({
                    "account_name": "dummy",
                    "account_key": "dummy",
                })
            
            instance = provider_class(**dummy_config)
            return instance.get_credential_variables()
        except Exception:
            return {}
