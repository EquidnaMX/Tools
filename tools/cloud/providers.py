"""
Cloud provider abstraction layer.

Provides a unified interface for different cloud storage providers:
- AWS S3
- Google Cloud Storage
- Azure Blob Storage
- DigitalOcean Spaces
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Iterable, Any


class SyncDirection(Enum):
    """Synchronization direction for mirror mode."""

    DOWNLOAD = "download"  # Remote → Local (delete orphaned local files)
    UPLOAD = "upload"  # Local → Remote (delete orphaned remote files)
    BIDIRECTIONAL = "bidirectional"  # Both directions (careful!)


@dataclass
class CloudObject:
    """Represents a cloud storage object."""

    key: str
    size_bytes: int
    modified: Optional[str] = None
    etag: Optional[str] = None
    storage_class: Optional[str] = None


class CloudProvider(ABC):
    """Abstract base class for cloud storage providers."""

    def __init__(
        self,
        bucket: str,
        dest: str,
        prefix: str = "",
        workers: int = 16,
        delete: bool = False,
        dry_run: bool = False,
        exclude: Optional[List[str]] = None,
        show_progress: bool = True,
        use_cache: bool = True,
        sync_direction: SyncDirection = SyncDirection.DOWNLOAD,
        compress: bool = False,
        compression_type: str = "gzip",
        encrypt: bool = False,
        encryption_key: Optional[str] = None,
        bandwidth_limit: Optional[int] = None,
        multipart_threshold: int = 100,
    ):
        """
        Initialize cloud provider.

        Args:
            bucket: Cloud bucket/container name
            dest: Local destination directory
            prefix: Optional prefix for objects
            workers: Number of parallel workers
            delete: Enable mirror mode (delete orphaned files)
            dry_run: Simulation mode
            exclude: Patterns to exclude
            show_progress: Show progress bars
            use_cache: Use local cache to skip unchanged files
            sync_direction: Direction for mirror mode (DOWNLOAD, UPLOAD, BIDIRECTIONAL)
            compress: Enable compression before upload (gzip or lz4)
            compression_type: Compression algorithm ('gzip' or 'lz4')
            encrypt: Enable client-side encryption (AES-256-GCM)
            encryption_key: Encryption key (32 bytes hex). Auto-generated if not provided.
            bandwidth_limit: Bandwidth limit in KB/s (None = unlimited)
            multipart_threshold: File size threshold for multipart upload in MB (default: 100MB)
        """
        self.bucket = bucket
        self.dest_root = Path(dest).resolve()
        self.prefix = prefix
        self.workers = workers
        self.delete = delete
        self.dry_run = dry_run
        self.exclude = exclude or []
        self.show_progress = show_progress
        self.use_cache = use_cache
        self.sync_direction = sync_direction
        self.compress = compress
        self.compression_type = compression_type
        self.encrypt = encrypt
        self.encryption_key = encryption_key
        self.bandwidth_limit = bandwidth_limit
        self.multipart_threshold = (
            multipart_threshold * 1024 * 1024
        )  # Convert MB to bytes
        self.client = None
        self._cache = None
        self._bandwidth_limiter = None

        # Validate compression type
        if self.compress and self.compression_type not in ("gzip", "lz4"):
            raise ValueError(
                f"Invalid compression_type: {self.compression_type}. Must be 'gzip' or 'lz4'"
            )

        # Generate or validate encryption key
        if self.encrypt:
            if self.encryption_key is None:
                # Auto-generate key and warn user
                import secrets

                self.encryption_key = secrets.token_hex(32)
                print(f"WARNING: Auto-generated encryption key: {self.encryption_key}")
                print("Store this key securely. You will need it to decrypt files.")
            elif len(bytes.fromhex(self.encryption_key)) != 32:
                raise ValueError("Encryption key must be 32 bytes (64 hex characters)")

        # Initialize bandwidth limiter if needed
        if self.bandwidth_limit:
            from tools.cloud.bandwidth import BandwidthLimiter

            self._bandwidth_limiter = BandwidthLimiter(
                self.bandwidth_limit * 1024
            )  # Convert KB/s to bytes/s

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name (e.g., 'AWS S3', 'Google Cloud Storage')."""
        pass

    @abstractmethod
    def _build_client(self) -> Any:
        """Build and configure cloud client."""
        pass

    @abstractmethod
    def _validate_credentials(self) -> bool:
        """Validate cloud credentials."""
        pass

    @abstractmethod
    def _list_objects(self) -> Iterable[CloudObject]:
        """List objects in bucket."""
        pass

    @abstractmethod
    def _download_object(self, obj: CloudObject, local_path: Path) -> bool:
        """Download single object from cloud."""
        pass

    @abstractmethod
    def _upload_object(self, local_path: Path, cloud_key: str) -> bool:
        """Upload single object to cloud."""
        pass

    @abstractmethod
    def _delete_object(self, key: str) -> bool:
        """Delete object from cloud."""
        pass

    @abstractmethod
    def _get_object_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata (size, etag, modified, etc.)."""
        pass

    def _should_exclude(self, key: str) -> bool:
        """Check if key matches any exclude pattern."""
        from fnmatch import fnmatch

        for pattern in self.exclude:
            if fnmatch(key, pattern):
                return True
        return False

    def _get_local_path(self, key: str) -> Path:
        """Convert cloud key to local path."""
        local_path = self.dest_root / key
        return local_path

    def sync(self) -> Dict[str, Any]:
        """
        Synchronize cloud bucket to local directory.

        Returns:
            Dictionary with sync statistics
        """
        import logging
        from datetime import datetime

        logger = logging.getLogger(__name__)
        stats = {
            "total_objects": 0,
            "downloaded": 0,
            "skipped": 0,
            "deleted": 0,
            "errors": [],
            "start_time": datetime.now().isoformat(),
        }

        # Initialize cache if enabled
        cache = None
        sync_id = None
        if self.use_cache:
            from tools.cloud.cache import SyncCache

            cache = SyncCache()
            sync_id = cache.log_sync_start(self.provider_name, self.bucket, "sync")

        try:
            # Create destination directory
            self.dest_root.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ Destination directory ready: {self.dest_root}")

            # Validate credentials
            if not self._validate_credentials():
                logger.critical("✗ Credential validation failed. Aborting.")
                raise RuntimeError("Invalid credentials")

            # List remote objects
            logger.info(f"📦 Listing objects in {self.bucket}/{self.prefix or ''}...")
            objects = []
            total_bytes = 0

            for obj in self._list_objects():
                if self._should_exclude(obj.key):
                    logger.debug(f"⏭️  Excluded by pattern: {obj.key}")
                    continue
                objects.append(obj)
                total_bytes += obj.size_bytes

            stats["total_objects"] = len(objects)
            logger.info(
                f"📦 Objects found: {len(objects):,} | Total size: {total_bytes / (1024**3):.2f} GB"
            )

            # Determine what needs downloading
            logger.info("🔍 Checking which files need downloading...")
            to_download = []

            for obj in objects:
                local_path = self._get_local_path(obj.key)

                # Check cache first if enabled
                if cache and cache.is_file_cached(
                    self.provider_name, self.bucket, obj.key, obj.size_bytes, obj.etag
                ):
                    stats["skipped"] += 1
                    logger.debug(f"⏭️  Cached: {obj.key}")
                    continue

                # Check if local file is up to date
                if local_path.exists():
                    local_size = local_path.stat().st_size
                    if local_size == obj.size_bytes:
                        stats["skipped"] += 1
                        logger.debug(f"⏭️  Already up to date: {obj.key}")

                        # Add to cache for future runs
                        if cache:
                            cache.add_file(
                                self.provider_name,
                                self.bucket,
                                obj.key,
                                str(local_path),
                                obj.size_bytes,
                                remote_etag=obj.etag,
                                last_modified=obj.modified,
                            )
                        continue

                to_download.append(obj)

            logger.info(f"📥 Files to download/update: {len(to_download):,}")
            logger.info(f"⏭️  Files already up to date: {stats['skipped']:,}")

            # Download files
            if self.dry_run:
                logger.info(f"📋 [DRY-RUN] Would download {len(to_download)} files")
                stats["downloaded"] = len(to_download)
            else:
                for obj in to_download:
                    local_path = self._get_local_path(obj.key)
                    try:
                        if self._download_object(obj, local_path):
                            stats["downloaded"] += 1
                            logger.debug(f"✓ Downloaded: {obj.key}")

                            # Add to cache
                            if cache:
                                cache.add_file(
                                    self.provider_name,
                                    self.bucket,
                                    obj.key,
                                    str(local_path),
                                    obj.size_bytes,
                                    remote_etag=obj.etag,
                                    last_modified=obj.modified,
                                )
                        else:
                            stats["errors"].append(f"Failed to download: {obj.key}")
                    except Exception as e:
                        error_msg = f"{obj.key}: {e}"
                        stats["errors"].append(error_msg)
                        logger.error(f"✗ Download error: {error_msg}")

            # Mirror mode: delete orphaned files based on direction
            if self.delete and self.sync_direction in [
                SyncDirection.DOWNLOAD,
                SyncDirection.BIDIRECTIONAL,
            ]:
                logger.info("🔍 DELETE mode: searching for orphaned local files...")
                remote_keys = {obj.key for obj in objects}

                for local_path in self.dest_root.rglob("*"):
                    if not local_path.is_file():
                        continue

                    # Convert local path to cloud key
                    rel_path = local_path.relative_to(self.dest_root).as_posix()
                    expected_key = (
                        f"{self.prefix.rstrip('/')}/{rel_path}"
                        if self.prefix
                        else rel_path
                    )

                    if expected_key not in remote_keys and not self._should_exclude(
                        expected_key
                    ):
                        logger.warning(f"🗑️  Orphan found (local): {local_path}")
                        if not self.dry_run:
                            try:
                                local_path.unlink(missing_ok=True)
                                stats["deleted"] += 1
                                logger.info(f"✓ Deleted: {local_path}")

                                # Remove from cache
                                if cache:
                                    cache.remove_file(
                                        self.provider_name, self.bucket, expected_key
                                    )
                            except OSError as e:
                                stats["errors"].append(f"Delete {local_path}: {e}")
                                logger.error(f"✗ Delete error: {e}")

            # Summary
            stats["end_time"] = datetime.now().isoformat()
            logger.info("=" * 60)
            logger.info("📊 SYNC SUMMARY")
            logger.info("=" * 60)
            logger.info(f"  Total remote objects:    {stats['total_objects']:,}")
            logger.info(
                f"  Downloaded/updated:      {stats['downloaded']:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            logger.info(f"  Already up to date:      {stats['skipped']:,}")
            if self.delete:
                logger.info(
                    f"  Deleted (orphans):       {stats['deleted']:,}{' (DRY-RUN)' if self.dry_run else ''}"
                )
            if stats["errors"]:
                logger.error(f"  ⚠️  Errors:             {len(stats['errors'])}")
                for err in stats["errors"][:5]:
                    logger.error(f"      - {err}")
                if len(stats["errors"]) > 5:
                    logger.error(f"      ... and {len(stats['errors']) - 5} more")
            logger.info("=" * 60)

            if stats["errors"]:
                logger.warning("⚠️  SYNC COMPLETED WITH ERRORS")
            else:
                logger.info("✅ SYNC COMPLETED SUCCESSFULLY")

            # Log completion to cache
            if cache and sync_id:
                cache.log_sync_complete(
                    sync_id,
                    files_synced=stats["downloaded"],
                    bytes_transferred=sum(
                        obj.size_bytes for obj in to_download[: stats["downloaded"]]
                    ),
                    errors=len(stats["errors"]),
                )
                cache.close()

            return stats

        except Exception as e:
            stats["end_time"] = datetime.now().isoformat()
            stats["errors"].append(f"Critical error: {e}")
            logger.critical(f"✗ Critical error: {e}", exc_info=True)
            raise

    def upload(self, source: str, dest_prefix: str = "", **kwargs) -> Dict[str, Any]:
        """
        Upload local directory or file to cloud bucket.

        Args:
            source: Local file or directory path to upload
            dest_prefix: Destination prefix/path in bucket
            **kwargs: Additional upload options (acl, content_type, etc.)

        Returns:
            Dictionary with upload statistics
        """
        import logging
        from datetime import datetime
        from pathlib import Path

        logger = logging.getLogger(__name__)
        stats = {
            "total_files": 0,
            "uploaded": 0,
            "updated": 0,
            "skipped": 0,
            "deleted": 0,
            "errors": [],
            "start_time": datetime.now().isoformat(),
        }

        # Initialize cache if enabled
        cache = None
        sync_id = None
        if self.use_cache:
            from tools.cloud.cache import SyncCache

            cache = SyncCache()
            sync_id = cache.log_sync_start(self.provider_name, self.bucket, "upload")

        try:
            source_path = Path(source).resolve()

            # Validate source exists
            if not source_path.exists():
                raise FileNotFoundError(f"Source not found: {source}")

            # Validate credentials
            if not self._validate_credentials():
                logger.critical("✗ Credential validation failed. Aborting.")
                raise RuntimeError("Invalid credentials")

            # Determine files to upload
            files_to_upload = []
            local_keys = set()

            if source_path.is_file():
                # Single file upload
                files_to_upload.append(source_path)
            else:
                # Directory upload - recursively find all files
                for file_path in source_path.rglob("*"):
                    if file_path.is_file():
                        # Check exclusion patterns
                        rel_path = file_path.relative_to(source_path).as_posix()
                        if not self._should_exclude(rel_path):
                            files_to_upload.append(file_path)

            stats["total_files"] = len(files_to_upload)
            logger.info(f"📁 Files to upload: {len(files_to_upload):,}")

            # Upload each file
            for file_path in files_to_upload:
                try:
                    # Determine cloud key
                    if source_path.is_file():
                        # Single file: use filename or specified dest_prefix
                        cloud_key = dest_prefix if dest_prefix else file_path.name
                    else:
                        # Directory: preserve structure under dest_prefix
                        rel_path = file_path.relative_to(source_path).as_posix()
                        if dest_prefix:
                            cloud_key = f"{dest_prefix.rstrip('/')}/{rel_path}"
                        else:
                            cloud_key = rel_path

                    local_keys.add(cloud_key)
                    local_size = file_path.stat().st_size

                    # Check cache first if enabled
                    if cache:
                        cached_info = cache.get_file(
                            self.provider_name, self.bucket, cloud_key
                        )
                        if cached_info and cached_info.get("size_bytes") == local_size:
                            # Check if file modification time hasn't changed
                            local_mtime = file_path.stat().st_mtime
                            cached_mtime = cached_info.get("last_modified")
                            if (
                                cached_mtime
                                and abs(local_mtime - cached_mtime.timestamp()) < 1
                            ):
                                stats["skipped"] += 1
                                logger.debug(f"⏭️  Cached: {cloud_key}")
                                continue

                    # Check if file already exists in cloud
                    metadata = self._get_object_metadata(cloud_key)

                    if metadata and metadata.get("size_bytes") == local_size:
                        stats["skipped"] += 1
                        logger.debug(f"⏭️  Already up to date: {cloud_key}")

                        # Add to cache for future runs
                        if cache:
                            cache.add_file(
                                self.provider_name,
                                self.bucket,
                                cloud_key,
                                str(file_path),
                                local_size,
                                remote_etag=metadata.get("etag"),
                                last_modified=datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ),
                            )
                        continue

                    # Upload file
                    if self.dry_run:
                        logger.info(
                            f"📋 [DRY-RUN] Would upload: {file_path} → {cloud_key}"
                        )
                        if metadata:
                            stats["updated"] += 1
                        else:
                            stats["uploaded"] += 1
                    else:
                        if self._upload_object(file_path, cloud_key):
                            if metadata:
                                stats["updated"] += 1
                                logger.info(f"✓ Updated: {cloud_key}")
                            else:
                                stats["uploaded"] += 1
                                logger.info(f"✓ Uploaded: {cloud_key}")

                            # Add to cache
                            if cache:
                                # Re-fetch metadata to get etag
                                new_metadata = self._get_object_metadata(cloud_key)
                                cache.add_file(
                                    self.provider_name,
                                    self.bucket,
                                    cloud_key,
                                    str(file_path),
                                    local_size,
                                    remote_etag=(
                                        new_metadata.get("etag")
                                        if new_metadata
                                        else None
                                    ),
                                    last_modified=datetime.fromtimestamp(
                                        file_path.stat().st_mtime
                                    ),
                                )
                        else:
                            stats["errors"].append(f"Failed to upload: {file_path}")

                except Exception as e:
                    error_msg = f"{file_path}: {e}"
                    stats["errors"].append(error_msg)
                    logger.error(f"✗ Upload error: {error_msg}")

            # Mirror mode: delete orphaned remote files based on direction
            if self.delete and self.sync_direction in [
                SyncDirection.UPLOAD,
                SyncDirection.BIDIRECTIONAL,
            ]:
                logger.info("🔍 DELETE mode: searching for orphaned remote files...")

                # List all remote objects
                for obj in self._list_objects():
                    if obj.key not in local_keys and not self._should_exclude(obj.key):
                        logger.warning(f"🗑️  Orphan found (remote): {obj.key}")
                        if not self.dry_run:
                            try:
                                if self._delete_object(obj.key):
                                    stats["deleted"] += 1
                                    logger.info(f"✓ Deleted: {obj.key}")

                                    # Remove from cache
                                    if cache:
                                        cache.remove_file(
                                            self.provider_name, self.bucket, obj.key
                                        )
                                else:
                                    stats["errors"].append(
                                        f"Failed to delete: {obj.key}"
                                    )
                            except Exception as e:
                                stats["errors"].append(f"Delete {obj.key}: {e}")
                                logger.error(f"✗ Delete error: {e}")

            # Summary
            stats["end_time"] = datetime.now().isoformat()
            logger.info("=" * 60)
            logger.info("📊 UPLOAD SUMMARY")
            logger.info("=" * 60)
            logger.info(f"  Total files:         {stats['total_files']:,}")
            logger.info(
                f"  Uploaded (new):      {stats['uploaded']:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            logger.info(
                f"  Updated:             {stats['updated']:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            logger.info(f"  Already up to date:  {stats['skipped']:,}")
            if self.delete:
                logger.info(
                    f"  Deleted (orphans):   {stats['deleted']:,}{' (DRY-RUN)' if self.dry_run else ''}"
                )
            if stats["errors"]:
                logger.error(f"  ⚠️  Errors:          {len(stats['errors'])}")
                for err in stats["errors"][:5]:
                    logger.error(f"      - {err}")
                if len(stats["errors"]) > 5:
                    logger.error(f"      ... and {len(stats['errors']) - 5} more")
            logger.info("=" * 60)

            if stats["errors"]:
                logger.warning("⚠️  UPLOAD COMPLETED WITH ERRORS")
            else:
                logger.info("✅ UPLOAD COMPLETED SUCCESSFULLY")

            # Log completion to cache
            if cache and sync_id:
                cache.log_sync_complete(
                    sync_id,
                    files_synced=stats["uploaded"] + stats["updated"],
                    bytes_transferred=sum(
                        f.stat().st_size
                        for f in files_to_upload[: stats["uploaded"] + stats["updated"]]
                    ),
                    errors=len(stats["errors"]),
                )
                cache.close()

            return stats

        except Exception as e:
            stats["end_time"] = datetime.now().isoformat()
            stats["errors"].append(f"Critical error: {e}")
            logger.critical(f"✗ Critical error: {e}", exc_info=True)
            raise

    def get_credential_variables(self) -> Dict[str, str]:
        """
        Return environment variable names required for this provider.

        Returns:
            Dict mapping variable names to descriptions
        """
        raise NotImplementedError("Subclass must implement get_credential_variables()")
