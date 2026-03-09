"""
Google Cloud Storage provider implementation.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, List

try:
    from google.cloud import storage
    from google.oauth2 import service_account
    from google.api_core.exceptions import GoogleAPICallError, NotFound
    HAS_GCS = True
except ImportError:
    HAS_GCS = False

from tools.cloud.providers import CloudProvider, CloudObject
from tools.core.logger import get_logger


class GCSProvider(CloudProvider):
    """Google Cloud Storage provider."""
    
    def __init__(self,
                 bucket: str,
                 dest: str,
                 project_id: Optional[str] = None,
                 credentials_path: Optional[str] = None,
                 prefix: str = "",
                 workers: int = 16,
                 delete: bool = False,
                 dry_run: bool = False,
                 exclude: Optional[List[str]] = None,
                 show_progress: bool = True,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize Google Cloud Storage provider.
        
        Args:
            bucket: GCS bucket name
            dest: Local destination directory
            project_id: GCP project ID
            credentials_path: Path to service account JSON file
            prefix: Optional object prefix
            workers: Number of parallel workers
            delete: Mirror mode
            dry_run: Simulation mode
            exclude: Patterns to exclude
            show_progress: Show progress bars
            logger: Logger instance
        """
        if not HAS_GCS:
            raise ImportError(
                "Google Cloud Storage support not available. "
                "Install google-cloud-storage with: pip install google-cloud-storage"
            )
        
        super().__init__(
            bucket=bucket,
            dest=dest,
            prefix=prefix,
            workers=workers,
            delete=delete,
            dry_run=dry_run,
            exclude=exclude,
            show_progress=show_progress
        )
        
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.logger = logger or get_logger(__name__)
        
        self._build_client()
    
    @property
    def provider_name(self) -> str:
        """Return provider name."""
        project = self.project_id or "default"
        return f"Google Cloud Storage ({project})"
    
    def _build_client(self) -> Any:
        """Build and configure GCS client."""
        try:
            if self.credentials_path:
                self.logger.info(f"📌 Using service account: {self.credentials_path}")
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self.client = storage.Client(
                    project=self.project_id,
                    credentials=credentials
                )
            else:
                self.logger.info("📌 Using Application Default Credentials")
                self.client = storage.Client(project=self.project_id)
            
            self.logger.info(f"✓ GCS client created for project: {self.project_id}")
            return self.client
            
        except Exception as e:
            self.logger.error(f"✗ Failed to create GCS client: {e}")
            raise
    
    def _validate_credentials(self) -> bool:
        """Validate GCS credentials."""
        try:
            bucket = self.client.bucket(self.bucket)
            bucket.reload()
            self.logger.info(f"✓ Valid credentials | GCS bucket accessible: {self.bucket}")
            return True
        except NotFound:
            self.logger.error(f"✗ GCS bucket not found: {self.bucket}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Credential validation failed: {e}")
            return False
    
    def _list_objects(self) -> Iterable[CloudObject]:
        """List objects in GCS bucket."""
        try:
            bucket = self.client.bucket(self.bucket)
            blobs = bucket.list_blobs(prefix=self.prefix)
            
            for blob in blobs:
                # Skip prefix itself if exists as object
                if blob.name == self.prefix:
                    continue
                
                yield CloudObject(
                    key=blob.name,
                    size_bytes=blob.size,
                    modified=blob.updated.isoformat() if blob.updated else None,
                    etag=blob.etag,
                    storage_class=blob.storage_class
                )
        
        except Exception as e:
            self.logger.error(f"✗ Failed to list GCS objects: {e}")
            raise
    
    def _download_object(self, obj: CloudObject, local_path: Path) -> bool:
        """Download object from GCS."""
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            bucket = self.client.bucket(self.bucket)
            blob = bucket.blob(obj.key)
            blob.download_to_filename(str(local_path))
            self.logger.debug(f"Downloaded: {obj.key} → {local_path}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to download {obj.key}: {e}")
            return False
    
    def _upload_object(self, local_path: Path, cloud_key: str) -> bool:
        """Upload object to GCS."""
        try:
            bucket = self.client.bucket(self.bucket)
            blob = bucket.blob(cloud_key)
            blob.upload_from_filename(str(local_path))
            self.logger.debug(f"Uploaded: {local_path} → {cloud_key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to upload {cloud_key}: {e}")
            return False
    
    def _delete_object(self, key: str) -> bool:
        """Delete object from GCS."""
        try:
            bucket = self.client.bucket(self.bucket)
            blob = bucket.blob(key)
            blob.delete()
            self.logger.debug(f"Deleted: {key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to delete {key}: {e}")
            return False
    
    def _get_object_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata from GCS."""
        try:
            bucket = self.client.bucket(self.bucket)
            blob = bucket.get_blob(key)
            
            if blob is None:
                return None
            
            return {
                "size_bytes": blob.size,
                "etag": blob.etag,
                "modified": blob.updated,
                "storage_class": blob.storage_class,
                "content_type": blob.content_type,
            }
        except Exception as e:
            self.logger.debug(f"Failed to get metadata for {key}: {e}")
            return None
    
    def get_credential_variables(self) -> Dict[str, str]:
        """Return required environment variables."""
        return {
            "GOOGLE_CLOUD_PROJECT": "GCP project ID",
            "GOOGLE_APPLICATION_CREDENTIALS": "Path to service account JSON file",
        }
