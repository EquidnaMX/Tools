"""Backup manager for local filesystem backups with retention rotation."""

from __future__ import annotations

import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Optional


class BackupError(Exception):
    """Raised when backup operations fail."""


@dataclass(frozen=True)
class BackupItem:
    """Represents a backup artifact on disk."""

    path: Path
    created_at: float


class BackupManager:
    """Create, list, restore, and rotate local .tar.gz backups."""

    def __init__(self, backup_dir: Path | str, keep: int = 7):
        self.backup_dir = Path(backup_dir).expanduser().resolve()
        self.keep = keep
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, source: Path | str, name: Optional[str] = None) -> Path:
        """Create a gzipped tar backup from a file or directory."""
        src = Path(source).expanduser().resolve()
        if not src.exists():
            raise BackupError(f"Source not found: {src}")

        backup_name = self._build_backup_name(src, name)
        target = self.backup_dir / backup_name

        mode = "w:gz"
        with tarfile.open(target, mode) as tar:
            tar.add(src, arcname=src.name)

        return target

    def list_backups(self, prefix: Optional[str] = None) -> List[BackupItem]:
        """List backups sorted by newest first."""
        items: List[BackupItem] = []
        for file in self.backup_dir.glob("*.tar.gz"):
            if prefix and not file.name.startswith(prefix):
                continue
            stat = file.stat()
            items.append(BackupItem(path=file, created_at=stat.st_mtime))

        items.sort(key=lambda i: i.created_at, reverse=True)
        return items

    def apply_rotation(
        self, prefix: Optional[str] = None, keep: Optional[int] = None
    ) -> List[Path]:
        """Delete old backups and keep only the newest N entries."""
        keep_count = self.keep if keep is None else keep
        if keep_count < 0:
            raise BackupError("keep must be >= 0")

        backups = self.list_backups(prefix=prefix)
        deleted: List[Path] = []
        for item in backups[keep_count:]:
            item.path.unlink(missing_ok=True)
            deleted.append(item.path)
        return deleted

    def restore_backup(
        self, backup_file: Path | str, destination: Path | str, overwrite: bool = False
    ) -> Path:
        """Restore a backup archive into destination and return extracted root path."""
        archive = Path(backup_file).expanduser().resolve()
        if not archive.exists() or not archive.is_file():
            raise BackupError(f"Backup file not found: {archive}")

        dest = Path(destination).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            if not members:
                raise BackupError(f"Backup archive is empty: {archive}")

            root_name = members[0].name.split("/")[0]
            extracted_root = dest / root_name
            if extracted_root.exists() and not overwrite:
                raise BackupError(
                    f"Destination already contains '{root_name}'. Use overwrite=True to replace."
                )

            self._safe_extract(tar, dest)

        return extracted_root

    def _build_backup_name(self, source: Path, name: Optional[str]) -> str:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        base = name.strip() if name else source.name
        safe = "".join(
            ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in base
        )
        return f"{safe}_{stamp}.tar.gz"

    def _safe_extract(self, tar: tarfile.TarFile, destination: Path) -> None:
        """Constrain names and links, then filter again as each member is extracted."""
        dest_resolved = destination.resolve()
        if not hasattr(tarfile, "data_filter"):
            raise BackupError(
                "Safe restore requires a Python security update with tarfile.data_filter"
            )
        for member in tar.getmembers():
            # Backslashes and drive names have platform-dependent interpretations.
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or PureWindowsPath(member.name).drive
                or "\\" in member.name
            ):
                raise BackupError(f"Unsafe path in archive: {member.name}")
            target_path = (dest_resolved / member.name).resolve()
            try:
                target_path.relative_to(dest_resolved)
                if member.issym() or member.islnk():
                    link = PurePosixPath(member.linkname)
                    if (
                        link.is_absolute()
                        or PureWindowsPath(member.linkname).drive
                        or "\\" in member.linkname
                    ):
                        raise ValueError("Absolute or platform-specific link")
                    base = target_path.parent if member.issym() else dest_resolved
                    (base / member.linkname).resolve().relative_to(dest_resolved)
                elif not (member.isfile() or member.isdir()):
                    raise ValueError("Special archive member")
            except ValueError as exc:
                raise BackupError(
                    f"Unsafe path or link in archive: {member.name}"
                ) from exc
        try:
            # Revalidate against links created by earlier members, not only the
            # original destination tree. Explicit filtering is required on 3.8–3.13.
            tar.extractall(path=dest_resolved, filter=tarfile.data_filter)
        except (tarfile.TarError, OSError) as exc:
            raise BackupError(f"Unsafe or unreadable backup: {exc}") from exc
