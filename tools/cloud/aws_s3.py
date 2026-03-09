"""
AWS S3 cloud storage provider implementation.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, List

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    HAS_AWS = True
except ImportError:
    HAS_AWS = False

from tools.cloud.providers import CloudProvider, CloudObject
from tools.core.logger import get_logger


class S3Provider(CloudProvider):
    """AWS S3 storage provider."""
    
    def __init__(self,
                 bucket: str,
                 dest: str,
                 region: str = "us-east-1",
                 prefix: str = "",
                 profile: Optional[str] = None,
                 access_key: Optional[str] = None,
                 secret_key: Optional[str] = None,
                 workers: int = 16,
                 delete: bool = False,
                 dry_run: bool = False,
                 exclude: Optional[List[str]] = None,
                 show_progress: bool = True,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize AWS S3 provider.
        
        Args:
            bucket: S3 bucket name
            dest: Local destination directory
            region: AWS region (default: us-east-1)
            prefix: Optional object prefix
            profile: AWS profile name
            access_key: AWS Access Key ID
            secret_key: AWS Secret Access Key
            workers: Number of parallel workers
            delete: Mirror mode
            dry_run: Simulation mode
            exclude: Patterns to exclude
            show_progress: Show progress bars
            logger: Logger instance
        """
        if not HAS_AWS:
            raise ImportError(
                "AWS S3 support not available. "
                "Install boto3 with: pip install boto3"
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
        
        self.region = region
        self.profile = profile
        self.access_key = access_key
        self.secret_key = secret_key
        self.logger = logger or get_logger(__name__)
        
        # Disable EC2 metadata endpoint
        os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
        
        self._build_client()
    
    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return f"AWS S3 ({self.region})"
    
    def _build_client(self) -> Any:
        """Build and configure S3 client."""
        try:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
                self.logger.info(f"📌 Using AWS profile: {self.profile}")
            
            session = boto3.Session(**session_kwargs)
            
            self.client = session.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.access_key or os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=self.secret_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(
                    retries={"max_attempts": 10, "mode": "standard"},
                    read_timeout=120,
                    connect_timeout=30,
                ),
            )
            
            self.logger.info(f"✓ S3 client created for region: {self.region}")
            return self.client
            
        except Exception as e:
            self.logger.error(f"✗ Failed to create S3 client: {e}")
            raise
    
    def _validate_credentials(self) -> bool:
        """Validate AWS credentials."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            self.logger.info(f"✓ Valid credentials | S3 bucket accessible: {self.bucket}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                self.logger.error(f"✗ S3 bucket not found: {self.bucket}")
            elif error_code == "403":
                self.logger.error(f"✗ Access denied to S3 bucket: {self.bucket}")
            else:
                self.logger.error(f"✗ Credential validation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Unexpected error validating credentials: {e}")
            return False
    
    def _list_objects(self) -> Iterable[CloudObject]:
        """List objects in S3 bucket."""
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=self.bucket,
                Prefix=self.prefix
            )
            
            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        # Skip prefix itself if exists as object
                        if obj["Key"] == self.prefix:
                            continue
                        
                        yield CloudObject(
                            key=obj["Key"],
                            size_bytes=obj["Size"],
                            modified=obj["LastModified"].isoformat() if "LastModified" in obj else None,
                            etag=obj.get("ETag"),
                            storage_class=obj.get("StorageClass")
                        )
        
        except Exception as e:
            self.logger.error(f"✗ Failed to list S3 objects: {e}")
            raise
    
    def _download_object(self, obj: CloudObject, local_path: Path) -> bool:
        """Download object from S3."""
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket, obj.key, str(local_path))
            self.logger.debug(f"Downloaded: {obj.key} → {local_path}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to download {obj.key}: {e}")
            return False
    
    def _upload_object(self, local_path: Path, cloud_key: str) -> bool:
        """Upload object to S3."""
        try:
            self.client.upload_file(str(local_path), self.bucket, cloud_key)
            self.logger.debug(f"Uploaded: {local_path} → {cloud_key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to upload {cloud_key}: {e}")
            return False
    
    def _delete_object(self, key: str) -> bool:
        """Delete object from S3."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            self.logger.debug(f"Deleted: {key}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Failed to delete {key}: {e}")
            return False
    
    def _get_object_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata from S3."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return {
                "size_bytes": response.get("ContentLength"),
                "etag": response.get("ETag"),
                "modified": response.get("LastModified"),
                "storage_class": response.get("StorageClass"),
                "content_type": response.get("ContentType"),
            }
        except Exception as e:
            self.logger.debug(f"Failed to get metadata for {key}: {e}")
            return None
    
    def get_credential_variables(self) -> Dict[str, str]:
        """Return required environment variables."""
        return {
            "AWS_ACCESS_KEY_ID": "AWS Access Key ID",
            "AWS_SECRET_ACCESS_KEY": "AWS Secret Access Key",
            "AWS_DEFAULT_REGION": "AWS region (optional)",
        }
