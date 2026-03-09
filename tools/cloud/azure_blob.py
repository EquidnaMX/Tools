"""
Azure Blob Storage provider implementation.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, List

try:
    from azure.storage.blob import BlobServiceClient, BlobClient
    from azure.core.exceptions import ResourceNotFoundError, AzureError
    HAS_AZURE = True
except ImportError:
    HAS_AZURE = False

from tools.cloud.providers import CloudProvider, CloudObject
from tools.core.logger import get_logger


class AzureBlobProvider(CloudProvider):
    """Azure Blob Storage provider."""
    
    def __init__(self,
                 container: str,
                 dest: str,
                 account_name: Optional[str] = None,
                 account_key: Optional[str] = None,
                 connection_string: Optional[str] = None,
                 prefix: str = "",
                 workers: int = 16,
                 delete: bool = False,
                 dry_run: bool = False,
                 exclude: Optional[List[str]] = None,
                 show_progress: bool = True,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize Azure Blob Storage provider.
        
        Args:
            container: Azure container name
            dest: Local destination directory
            account_name: Azure storage account name
            account_key: Azure storage account key
            connection_string: Azure connection string (alternative to account_name/account_key)
            prefix: Optional blob prefix
            workers: Number of parallel workers
            delete: Mirror mode
            dry_run: Simulation mode
            exclude: Patterns to exclude
            show_progress: Show progress bars
            logger: Logger instance
        """
        if not HAS_AZURE:
            raise ImportError(
                "Azure Blob Storage support not available. "
                "Install azure-storage-blob with: pip install azure-storage-blob"
            )
        
        super().__init__(
            bucket=container,  # Azure calls it container, we map to bucket
            dest=dest,
            prefix=prefix,
            workers=workers,
            delete=delete,
            dry_run=dry_run,
            exclude=exclude,
            show_progress=show_progress
        )
        
        self.container = container
        self.account_name = account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        self.account_key = account_key or os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
        self.connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.logger = logger or get_logger(__name__)
        
        self._build_client()
    
    @property
    def provider_name(self) -> str:
        """Return provider name."""
        account = self.account_name or "default"
        return f"Azure Blob Storage ({account})"
    
    def _build_client(self) -> Any:
        """Build and configure Azure Blob Storage client."""
        try:
            if self.connection_string:
                self.logger.info("📌 Using connection string")
                self.client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
            elif self.account_name and self.account_key:
                self.logger.info(f"📌 Using account key for: {self.account_name}")
                account_url = f"https://{self.account_name}.blob.core.windows.net"
                self.client = BlobServiceClient(
                    account_url=account_url,
                    credential=self.account_key
                )
            else:
                raise ValueError(
                    "Must provide either connection_string or (account_name + account_key)"
                )
            
            self.logger.info(f"✓ Azure Blob Storage client created")
            return self.client
            
        except Exception as e:
            self.logger.error(f"✗ Failed to create Azure Blob Storage client: {e}")
            raise
    
    def _validate_credentials(self) -> bool:
        """Validate Azure credentials."""
        try:
            container_client = self.client.get_container_client(self.container)
            container_client.get_container_properties()
            self.logger.info(f"✓ Valid credentials | Container accessible: {self.container}")
            return True
        except ResourceNotFoundError:
            self.logger.error(f"✗ Azure container not found: {self.container}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Credential validation failed: {e}")
            return False
    
    def _list_objects(self) -> Iterable[CloudObject]:
        """List blobs in Azure container."""
        try:
            container_client = self.client.get_container_client(self.container)
            blobs = container_client.list_blobs(name_starts_with=self.prefix)
            
            for blob in blobs:
                # Skip prefix itself if exists as object
                if blob.name == self.prefix:
                    continue
                
                yield CloudObject(
                    key=blob.name,
                    size_bytes=blob.size,
                    modified=blob.last_modified.isoformat() if blob.last_modified else None,
                    etag=blob.etag,
                    storage_class=None  # Azure doesn't have storage classes like S3
                )
        
        except Exception as e:
            self.logger.error(f"✗ Failed to list Azure blobs: {e}")
            raise
    
    def _download_object(self, obj: CloudObject, local_path: Path) -> bool:
        """Download blob from Azure."""
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob_client = self.client.get_blob_client(
                container=self.container,
                blob=obj.key
            )
            
            with open(local_path, "wb") as f:
                blob_data = blob_client.download_blob()
                f.write(blob_data.readall())
            
            self.logger.debug(f"Downloaded: {obj.key} → {local_path}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to download {obj.key}: {e}")
            return False
    
    def _upload_object(self, local_path: Path, cloud_key: str) -> bool:
        """Upload blob to Azure."""
        try:
            blob_client = self.client.get_blob_client(
                container=self.container,
                blob=cloud_key
            )
            
            with open(local_path, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            
            self.logger.debug(f"Uploaded: {local_path} → {cloud_key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to upload {cloud_key}: {e}")
            return False
    
    def _delete_object(self, key: str) -> bool:
        """Delete blob from Azure."""
        try:
            blob_client = self.client.get_blob_client(
                container=self.container,
                blob=key
            )
            blob_client.delete_blob()
            self.logger.debug(f"Deleted: {key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to delete {key}: {e}")
            return False
    
    def _get_object_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get blob metadata from Azure."""
        try:
            blob_client = self.client.get_blob_client(
                container=self.container,
                blob=key
            )
            properties = blob_client.get_blob_properties()
            
            return {
                "size_bytes": properties.size,
                "etag": properties.etag,
                "modified": properties.last_modified,
                "storage_class": None,
                "content_type": properties.content_settings.content_type if properties.content_settings else None,
            }
        except Exception as e:
            self.logger.debug(f"Failed to get metadata for {key}: {e}")
            return None
    
    def get_credential_variables(self) -> Dict[str, str]:
        """Return required environment variables."""
        return {
            "AZURE_STORAGE_CONNECTION_STRING": "Azure connection string (easiest)",
            "AZURE_STORAGE_ACCOUNT_NAME": "Azure storage account name",
            "AZURE_STORAGE_ACCOUNT_KEY": "Azure storage account key",
        }
