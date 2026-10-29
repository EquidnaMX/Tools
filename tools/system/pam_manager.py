"""
PAM configuration manager utilities.

Provides safe operations to inspect and maintain files in /etc/pam.d.
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tools.core.exceptions import ToolsException
from tools.core.logger import get_logger

logger = get_logger(__name__)


# Security hardening profiles for common PAM services
HARDENING_PROFILES: Dict[str, List[str]] = {
    "sshd": [
        "# Security hardening for SSH",
        "auth       required     pam_env.so",
        "auth       required     pam_faillock.so preauth audit silent deny=3 unlock_time=600",
        "auth       [success=1 default=bad] pam_unix.so",
        "auth       [default=die] pam_faillock.so authfail audit deny=3 unlock_time=600",
        "auth       sufficient   pam_faillock.so authsucc audit deny=3 unlock_time=600",
        "account    required     pam_faillock.so",
        "account    required     pam_unix.so",
        "account    required     pam_time.so",
        "password   requisite    pam_pwquality.so retry=3 minlen=12 dcredit=-1 ucredit=-1 ocredit=-1 lcredit=-1",
        "password   sufficient   pam_unix.so sha512 shadow use_authtok",
        "password   required     pam_deny.so",
        "session    required     pam_limits.so",
        "session    required     pam_unix.so",
        "session    optional     pam_umask.so",
    ],
    "login": [
        "# Security hardening for console login",
        "auth       required     pam_securetty.so",
        "auth       required     pam_env.so",
        "auth       required     pam_faillock.so preauth audit silent deny=3 unlock_time=900",
        "auth       [success=1 default=bad] pam_unix.so",
        "auth       [default=die] pam_faillock.so authfail audit deny=3 unlock_time=900",
        "auth       sufficient   pam_faillock.so authsucc audit deny=3 unlock_time=900",
        "account    required     pam_faillock.so",
        "account    required     pam_access.so",
        "account    required     pam_unix.so",
        "account    required     pam_time.so",
        "password   requisite    pam_pwquality.so retry=3 minlen=14 dcredit=-1 ucredit=-1 ocredit=-1 lcredit=-1",
        "password   sufficient   pam_unix.so sha512 shadow use_authtok",
        "password   required     pam_deny.so",
        "session    required     pam_limits.so",
        "session    required     pam_unix.so",
        "session    optional     pam_lastlog.so",
        "session    optional     pam_mail.so standard",
    ],
    "su": [
        "# Security hardening for su command",
        "auth       sufficient   pam_rootok.so",
        "auth       required     pam_wheel.so use_uid",
        "auth       required     pam_env.so",
        "auth       required     pam_faillock.so preauth audit silent deny=3 unlock_time=900",
        "auth       [success=1 default=bad] pam_unix.so",
        "auth       [default=die] pam_faillock.so authfail audit deny=3 unlock_time=900",
        "auth       sufficient   pam_faillock.so authsucc audit deny=3 unlock_time=900",
        "account    required     pam_faillock.so",
        "account    required     pam_unix.so",
        "password   sufficient   pam_unix.so sha512 shadow",
        "password   required     pam_deny.so",
        "session    required     pam_limits.so",
        "session    required     pam_unix.so",
        "session    optional     pam_xauth.so",
    ],
}


class PAMManagerError(ToolsException):
    """Raised when PAM management operations fail."""


@dataclass
class PAMFileInfo:
    """Metadata for a PAM service file."""

    service: str
    path: Path
    exists: bool
    size_bytes: int = 0


@dataclass
class PAMUpdateResult:
    """Result of an update operation over a PAM file."""

    service: str
    updated: bool
    created: bool = False
    dry_run: bool = False
    backup_path: Optional[Path] = None
    diff: Optional[str] = None


@dataclass
class PAMHardeningResult:
    """Result of applying a hardening profile."""

    service: str
    profile: str
    applied: bool
    dry_run: bool = False
    backup_path: Optional[Path] = None
    diff: Optional[str] = None


def generate_diff(original: str, modified: str, filename: str = "PAM file") -> str:
    """Generate unified diff between two text strings."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"{filename} (original)",
        tofile=f"{filename} (modified)",
        lineterm="",
    )

    return "".join(diff_lines)


class PAMManager:
    """Manage PAM files with backup-friendly operations."""

    def __init__(self, pam_dir: Path | str = "/etc/pam.d"):
        self.pam_dir = Path(pam_dir)

    def _service_path(self, service: str) -> Path:
        if not service or "/" in service or "\\" in service:
            raise PAMManagerError(f"Invalid PAM service name: {service}")
        return self.pam_dir / service

    def list_services(self) -> List[PAMFileInfo]:
        """List PAM service files in pam_dir."""
        if not self.pam_dir.exists():
            raise PAMManagerError(f"PAM directory not found: {self.pam_dir}")
        if not self.pam_dir.is_dir():
            raise PAMManagerError(f"Not a directory: {self.pam_dir}")

        services: List[PAMFileInfo] = []
        for file_path in sorted(self.pam_dir.iterdir()):
            if not file_path.is_file():
                continue
            services.append(
                PAMFileInfo(
                    service=file_path.name,
                    path=file_path,
                    exists=True,
                    size_bytes=file_path.stat().st_size,
                )
            )
        return services

    def read_service(self, service: str) -> str:
        """Read a PAM service file as UTF-8 text."""
        file_path = self._service_path(service)
        if not file_path.exists():
            raise PAMManagerError(f"PAM service file not found: {file_path}")

        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PAMManagerError(f"Could not read file {file_path}: {exc}") from exc

    def check_module_enabled(self, service: str, module_name: str) -> bool:
        """Check if a PAM module appears enabled in the service file."""
        if not module_name:
            raise PAMManagerError("module_name cannot be empty")

        content = self.read_service(service)
        pattern = re.compile(
            rf"^\s*(auth|account|password|session)\s+\S+\s+{re.escape(module_name)}(\s|$)"
        )
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if pattern.search(line):
                return True
        return False

    def create_backup(self, service: str, backup_dir: Path | str) -> Path:
        """Create timestamped backup for a PAM service file."""
        source = self._service_path(service)
        if not source.exists():
            raise PAMManagerError(f"PAM service file not found: {source}")

        backup_root = Path(backup_dir)
        backup_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_root / f"{service}.{timestamp}.bak"

        try:
            shutil.copy2(source, backup_path)
            logger.info("Created PAM backup: %s", backup_path)
            return backup_path
        except OSError as exc:
            raise PAMManagerError(
                f"Could not create backup {backup_path}: {exc}"
            ) from exc

    def restore_backup(
        self, service: str, backup_file: Path | str, dry_run: bool = False
    ) -> bool:
        """Restore a backup file over the PAM service file."""
        target = self._service_path(service)
        backup_path = Path(backup_file)

        if not backup_path.exists():
            raise PAMManagerError(f"Backup file not found: {backup_path}")

        if dry_run:
            logger.info("[DRY-RUN] Would restore %s -> %s", backup_path, target)
            return True

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target)
            logger.info("Restored PAM backup: %s -> %s", backup_path, target)
            return True
        except OSError as exc:
            raise PAMManagerError(
                f"Could not restore backup {backup_path}: {exc}"
            ) from exc

    def ensure_line(
        self,
        service: str,
        line: str,
        match_pattern: Optional[str] = None,
        after_pattern: Optional[str] = None,
        backup_dir: Optional[Path | str] = None,
        dry_run: bool = False,
        show_diff: bool = False,
    ) -> PAMUpdateResult:
        """
        Ensure a line exists in the service file.

        If match_pattern is provided and a line matches it, that line is replaced.
        Otherwise, if exact line does not exist, it is appended or inserted after
        after_pattern if provided.

        Args:
            service: PAM service name
            line: Line to ensure in the file
            match_pattern: Optional regex pattern to find and replace existing line
            after_pattern: Optional regex pattern to insert line after
            backup_dir: Optional directory to store backup before changes
            dry_run: If True, show what would happen without making changes
            show_diff: If True, generate unified diff of changes
        """
        if not line.strip():
            raise PAMManagerError("line cannot be empty")

        path = self._service_path(service)
        if not path.exists():
            raise PAMManagerError(f"PAM service file not found: {path}")

        content = self.read_service(service)
        lines = content.splitlines()
        updated_lines = lines.copy()

        updated = False
        created = False

        matcher = re.compile(match_pattern) if match_pattern else None
        insert_after = re.compile(after_pattern) if after_pattern else None

        if matcher:
            for idx, existing in enumerate(updated_lines):
                if matcher.search(existing):
                    if existing != line:
                        updated_lines[idx] = line
                        updated = True
                    break
            else:
                # No match found, continue with insertion rules below
                pass

        if not updated and line not in updated_lines:
            if insert_after:
                insert_idx = -1
                for idx, existing in enumerate(updated_lines):
                    if insert_after.search(existing):
                        insert_idx = idx
                if insert_idx >= 0:
                    updated_lines.insert(insert_idx + 1, line)
                    updated = True
                    created = True
                else:
                    updated_lines.append(line)
                    updated = True
                    created = True
            else:
                updated_lines.append(line)
                updated = True
                created = True

        backup_path: Optional[Path] = None
        if updated and backup_dir is not None:
            backup_path = self.create_backup(service, backup_dir)

        diff_output: Optional[str] = None
        if updated and show_diff:
            original_content = content
            modified_content = "\n".join(updated_lines) + "\n"
            diff_output = generate_diff(original_content, modified_content, str(path))

        if updated and not dry_run:
            try:
                path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            except OSError as exc:
                raise PAMManagerError(
                    f"Could not write PAM file {path}: {exc}"
                ) from exc

        if updated and dry_run:
            logger.info("[DRY-RUN] Would update PAM file: %s", path)

        return PAMUpdateResult(
            service=service,
            updated=updated,
            created=created,
            dry_run=dry_run,
            backup_path=backup_path,
            diff=diff_output,
        )

    def apply_hardening(
        self,
        service: str,
        profile: Optional[str] = None,
        backup_dir: Optional[Path | str] = None,
        dry_run: bool = False,
        show_diff: bool = False,
    ) -> PAMHardeningResult:
        """
        Apply a security hardening profile to a PAM service.

        Args:
            service: PAM service name (e.g., 'sshd', 'login', 'su')
            profile: Hardening profile name. If None, uses service name as profile
            backup_dir: Optional directory to store backup before changes
            dry_run: If True, show what would happen without making changes
            show_diff: If True, generate unified diff of changes

        Returns:
            PAMHardeningResult with status and optional diff

        Raises:
            PAMManagerError: If profile not found or service file doesn't exist
        """
        profile_name = profile or service

        if profile_name not in HARDENING_PROFILES:
            available = ", ".join(sorted(HARDENING_PROFILES.keys()))
            raise PAMManagerError(
                f"Unknown hardening profile: {profile_name}. "
                f"Available profiles: {available}"
            )

        path = self._service_path(service)
        if not path.exists():
            raise PAMManagerError(f"PAM service file not found: {path}")

        # Read current content
        original_content = self.read_service(service)

        # Apply hardening profile
        profile_lines = HARDENING_PROFILES[profile_name]
        new_content = "\n".join(profile_lines) + "\n"

        # Check if already applied
        if original_content == new_content:
            return PAMHardeningResult(
                service=service,
                profile=profile_name,
                applied=False,
                dry_run=dry_run,
                diff=None,
            )

        # Create backup if requested
        backup_path: Optional[Path] = None
        if backup_dir is not None:
            backup_path = self.create_backup(service, backup_dir)

        # Generate diff if requested
        diff_output: Optional[str] = None
        if show_diff:
            diff_output = generate_diff(original_content, new_content, str(path))

        # Apply changes unless dry-run
        if not dry_run:
            try:
                path.write_text(new_content, encoding="utf-8")
                logger.info("Applied %s hardening profile to %s", profile_name, service)
            except OSError as exc:
                raise PAMManagerError(
                    f"Could not write PAM file {path}: {exc}"
                ) from exc
        else:
            logger.info(
                "[DRY-RUN] Would apply %s hardening profile to %s",
                profile_name,
                service,
            )

        return PAMHardeningResult(
            service=service,
            profile=profile_name,
            applied=True,
            dry_run=dry_run,
            backup_path=backup_path,
            diff=diff_output,
        )
