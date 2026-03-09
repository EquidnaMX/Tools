"""
Cloud storage module for tools CLI.

Provides cloud storage synchronization capabilities for:
- AWS S3
- Google Cloud Storage
- Azure Blob Storage
- DigitalOcean Spaces (S3-compatible)

Main classes:
- CloudProvider: Abstract base class for cloud providers
- S3Provider: AWS S3 implementation (requires boto3)
- GCSProvider: Google Cloud Storage implementation (requires google-cloud-storage)
- AzureBlobProvider: Azure Blob Storage implementation (requires azure-storage-blob)
- DigitalOceanSync: DigitalOcean Spaces synchronization (legacy)
- ConfigManager: Manages YAML configuration profiles
- CloudProviderFactory: Factory for creating provider instances
"""

from tools.cloud.providers import CloudProvider, CloudObject

# Import providers with optional dependencies
try:
    from tools.cloud.aws_s3 import S3Provider
except ImportError:
    S3Provider = None

try:
    from tools.cloud.google_cloud import GCSProvider
except ImportError:
    GCSProvider = None

try:
    from tools.cloud.azure_blob import AzureBlobProvider
except ImportError:
    AzureBlobProvider = None

from tools.cloud.factory import CloudProviderFactory
from tools.cloud.sync import DigitalOceanSync, SyncStats, UploadStats
from tools.cloud.config_manager import ConfigManager, ConfigProfile, ConfigError

__all__ = [
    # Base classes
    'CloudProvider',
    'CloudObject',
    
    # Provider implementations (may be None if dependencies not installed)
    'S3Provider',
    'GCSProvider',
    'AzureBlobProvider',
    'CloudProviderFactory',
    
    # Legacy DigitalOcean
    'DigitalOceanSync',
    'SyncStats',
    'UploadStats',
    
    # Configuration
    'ConfigManager',
    'ConfigProfile',
    'ConfigError',
]

__version__ = '2.7.0'
