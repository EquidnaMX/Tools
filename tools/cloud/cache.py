"""
Local cache system for tracking synchronized files.

Provides SQLite-based caching of file metadata to improve
sync performance by avoiding unnecessary downloads.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class SyncCache:
    """Local cache for tracking synchronized file states."""
    
    DEFAULT_CACHE_PATH = Path.home() / ".cloud-tools" / "sync_cache.db"
    
    def __init__(self, cache_path: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize sync cache.
        
        Args:
            cache_path: Path to SQLite database file (default: ~/.cloud-tools/sync_cache.db)
            logger: Logger instance
        """
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self.logger = logger or logging.getLogger(__name__)
        self._conn: Optional[sqlite3.Connection] = None
        self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Create cache database and tables if they don't exist."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = sqlite3.connect(str(self.cache_path))
        self._conn.row_factory = sqlite3.Row
        
        cursor = self._conn.cursor()
        
        # Create files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                bucket TEXT NOT NULL,
                remote_key TEXT NOT NULL,
                local_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                checksum TEXT,
                remote_etag TEXT,
                last_modified TEXT,
                synced_at TEXT NOT NULL,
                UNIQUE(provider, bucket, remote_key, local_path)
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_bucket_key 
            ON files(provider, bucket, remote_key)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_local_path 
            ON files(local_path)
        """)
        
        # Create sync_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                bucket TEXT NOT NULL,
                operation TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                files_synced INTEGER DEFAULT 0,
                bytes_transferred INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                status TEXT NOT NULL
            )
        """)
        
        self._conn.commit()
        self.logger.debug(f"Cache database initialized: {self.cache_path}")
    
    def add_file(self, 
                 provider: str,
                 bucket: str,
                 remote_key: str,
                 local_path: str,
                 file_size: int,
                 checksum: Optional[str] = None,
                 remote_etag: Optional[str] = None,
                 last_modified: Optional[str] = None) -> None:
        """
        Add or update file entry in cache.
        
        Args:
            provider: Cloud provider name (aws, gcs, azure, digitalocean)
            bucket: Bucket/container name
            remote_key: Remote object key
            local_path: Local file path
            file_size: File size in bytes
            checksum: File checksum (MD5, SHA256, etc.)
            remote_etag: Remote ETag
            last_modified: Last modified timestamp
        """
        cursor = self._conn.cursor()
        synced_at = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO files 
            (provider, bucket, remote_key, local_path, file_size, checksum, 
             remote_etag, last_modified, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (provider, bucket, remote_key, local_path, file_size, checksum,
              remote_etag, last_modified, synced_at))
        
        self._conn.commit()
        self.logger.debug(f"Cache updated: {remote_key} → {local_path}")
    
    def get_file(self, provider: str, bucket: str, remote_key: str) -> Optional[Dict[str, Any]]:
        """
        Get file entry from cache.
        
        Args:
            provider: Cloud provider name
            bucket: Bucket/container name
            remote_key: Remote object key
        
        Returns:
            File metadata dict or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT * FROM files 
            WHERE provider = ? AND bucket = ? AND remote_key = ?
            ORDER BY synced_at DESC
            LIMIT 1
        """, (provider, bucket, remote_key))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def is_file_cached(self, provider: str, bucket: str, remote_key: str, 
                       file_size: int, remote_etag: Optional[str] = None) -> bool:
        """
        Check if file is already cached and up-to-date.
        
        Args:
            provider: Cloud provider name
            bucket: Bucket/container name
            remote_key: Remote object key
            file_size: Current remote file size
            remote_etag: Current remote ETag
        
        Returns:
            True if file is cached and matches current remote state
        """
        cached = self.get_file(provider, bucket, remote_key)
        if not cached:
            return False
        
        # Check if local file still exists
        local_path = Path(cached["local_path"])
        if not local_path.exists():
            return False
        
        # Check if size matches
        if cached["file_size"] != file_size:
            return False
        
        # Check ETag if available
        if remote_etag and cached["remote_etag"]:
            if cached["remote_etag"] != remote_etag:
                return False
        
        return True
    
    def remove_file(self, provider: str, bucket: str, remote_key: str) -> None:
        """Remove file entry from cache."""
        cursor = self._conn.cursor()
        cursor.execute("""
            DELETE FROM files 
            WHERE provider = ? AND bucket = ? AND remote_key = ?
        """, (provider, bucket, remote_key))
        self._conn.commit()
        self.logger.debug(f"Removed from cache: {remote_key}")
    
    def clear_bucket(self, provider: str, bucket: str) -> int:
        """
        Clear all cached entries for a specific bucket.
        
        Args:
            provider: Cloud provider name
            bucket: Bucket/container name
        
        Returns:
            Number of entries removed
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            DELETE FROM files 
            WHERE provider = ? AND bucket = ?
        """, (provider, bucket))
        deleted = cursor.rowcount
        self._conn.commit()
        self.logger.info(f"Cleared {deleted} entries from cache for {provider}/{bucket}")
        return deleted
    
    def clear_all(self) -> int:
        """
        Clear entire cache.
        
        Returns:
            Number of entries removed
        """
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM files")
        deleted = cursor.rowcount
        self._conn.commit()
        self.logger.info(f"Cleared entire cache ({deleted} entries)")
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        cursor = self._conn.cursor()
        
        # Total files
        cursor.execute("SELECT COUNT(*) as count FROM files")
        total_files = cursor.fetchone()["count"]
        
        # Total size
        cursor.execute("SELECT SUM(file_size) as total FROM files")
        total_size = cursor.fetchone()["total"] or 0
        
        # Files by provider
        cursor.execute("""
            SELECT provider, COUNT(*) as count, SUM(file_size) as size
            FROM files
            GROUP BY provider
        """)
        by_provider = {row["provider"]: {"count": row["count"], "size": row["size"]} 
                      for row in cursor.fetchall()}
        
        # Files by bucket
        cursor.execute("""
            SELECT provider, bucket, COUNT(*) as count, SUM(file_size) as size
            FROM files
            GROUP BY provider, bucket
        """)
        by_bucket = [(row["provider"], row["bucket"], row["count"], row["size"]) 
                    for row in cursor.fetchall()]
        
        # Oldest and newest sync
        cursor.execute("SELECT MIN(synced_at) as oldest, MAX(synced_at) as newest FROM files")
        row = cursor.fetchone()
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_gb": total_size / (1024**3),
            "by_provider": by_provider,
            "by_bucket": by_bucket,
            "oldest_sync": row["oldest"],
            "newest_sync": row["newest"],
            "cache_path": str(self.cache_path)
        }
    
    def list_files(self, provider: Optional[str] = None, 
                   bucket: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """
        List cached files with optional filtering.
        
        Args:
            provider: Filter by provider
            bucket: Filter by bucket
            limit: Maximum number of results
        
        Returns:
            List of file metadata dicts
        """
        cursor = self._conn.cursor()
        
        query = "SELECT * FROM files"
        params = []
        
        conditions = []
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if bucket:
            conditions.append("bucket = ?")
            params.append(bucket)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY synced_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def log_sync_start(self, provider: str, bucket: str, operation: str) -> int:
        """
        Log the start of a sync operation.
        
        Args:
            provider: Cloud provider name
            bucket: Bucket name
            operation: Operation type (sync, upload)
        
        Returns:
            Sync history ID
        """
        cursor = self._conn.cursor()
        started_at = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO sync_history 
            (provider, bucket, operation, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
        """, (provider, bucket, operation, started_at))
        
        self._conn.commit()
        return cursor.lastrowid
    
    def log_sync_complete(self, sync_id: int, files_synced: int, 
                         bytes_transferred: int, errors: int) -> None:
        """
        Log the completion of a sync operation.
        
        Args:
            sync_id: Sync history ID
            files_synced: Number of files synced
            bytes_transferred: Bytes transferred
            errors: Number of errors
        """
        cursor = self._conn.cursor()
        completed_at = datetime.now().isoformat()
        status = "completed" if errors == 0 else "completed_with_errors"
        
        cursor.execute("""
            UPDATE sync_history 
            SET completed_at = ?, files_synced = ?, bytes_transferred = ?,
                errors = ?, status = ?
            WHERE id = ?
        """, (completed_at, files_synced, bytes_transferred, errors, status, sync_id))
        
        self._conn.commit()
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def calculate_file_checksum(file_path: Path, algorithm: str = "md5") -> str:
    """
    Calculate file checksum.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (md5, sha256)
    
    Returns:
        Hexadecimal checksum string
    """
    if algorithm.lower() == "md5":
        hasher = hashlib.md5()
    elif algorithm.lower() == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    
    return hasher.hexdigest()
