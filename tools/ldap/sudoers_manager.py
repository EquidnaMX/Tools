"""Constrained, validated and recoverable sudoers rule management."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import os
import re
import shutil
import subprocess
import tempfile


@dataclass
class SudoersRule:
    group: str
    run_as: str = "root"
    commands: str = "ALL"

    def to_line(self) -> str:
        for value in (self.group, self.run_as, self.commands):
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(c in value for c in "\r\n\0")
            ):
                raise ValueError("Sudoers fields must be nonempty single-line strings")
        clean_group = self.group[1:] if self.group.startswith("%") else self.group
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", clean_group):
            raise ValueError("Invalid sudoers group name")
        atom = r"!?(?:[A-Za-z_][A-Za-z0-9_.-]*|#[0-9]+|%[A-Za-z_][A-Za-z0-9_.-]*)"
        names = atom + r"(?:\s*,\s*" + atom + r")*"
        if not re.fullmatch(names + r"(?:\s*:\s*" + names + r")?", self.run_as):
            raise ValueError("Invalid run-as user/group list")
        return f"%{clean_group} ALL=({self.run_as}) {self.commands}"


class SudoersManager:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    @staticmethod
    def _target(file_name, sudoers_dir):
        # Dots and '~' are also forbidden: sudo ignores such include-dir names.
        if not isinstance(file_name, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", file_name
        ):
            raise ValueError(
                "Use a sudoers basename containing only letters, numbers, '-' or '_'"
            )
        directory = Path(sudoers_dir)
        if directory.is_symlink():
            raise ValueError("Refusing a symbolic-link sudoers directory")
        directory = directory.resolve()
        target = directory / file_name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Refusing a symbolic link or non-regular sudoers file")
        return target

    @staticmethod
    def _validate_file(path, visudo_path):
        try:
            result = subprocess.run(
                [visudo_path, "-cf", str(path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0:
                return True, "OK"
            return (
                False,
                (result.stderr or result.stdout or "visudo rejected the rule").strip(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    @staticmethod
    def _backup(target):
        # Backups must never become active sudoers include files.
        directory = target.parent.parent / "tools-sudoers-backups"
        if directory.is_symlink():
            raise ValueError("Refusing a symbolic-link backup directory")
        directory.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.stat()
        if os.name != "nt" and (
            metadata.st_mode & 0o022
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            raise ValueError(
                "Backup directory is writable by others or owned by another user"
            )
        fd, name = tempfile.mkstemp(prefix=target.name + "-", dir=str(directory))
        os.close(fd)
        try:
            shutil.copy2(target, name)
        except Exception:
            os.unlink(name)
            raise
        return Path(name)

    def create_rule_file(
        self,
        file_name,
        rule,
        sudoers_dir="/etc/sudoers.d",
        validate=True,
        visudo_path="visudo",
    ) -> Tuple[bool, str]:
        """Validation is mandatory on writes; legacy validate=False cannot bypass it."""
        staged: Optional[str] = None
        try:
            target = self._target(file_name, sudoers_dir)
            content = self._build_file_content(rule)
            if self.dry_run:
                return (
                    True,
                    f"[DRY-RUN] Se crearía {target}; visudo se exige al aplicar: {rule.to_line()}",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, staged = tempfile.mkstemp(prefix=".tools-rule-", dir=str(target.parent))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(staged, 0o440)
            valid, message = self._validate_file(staged, visudo_path)
            if not valid:
                return False, f"Validación sudoers falló: {message}"
            # Check the name again immediately before using the staged result.
            self._target(file_name, sudoers_dir)
            backup = self._backup(target) if target.exists() else None
            os.replace(staged, target)
            staged = None
            suffix = f"; respaldo: {backup}" if backup else ""
            return True, f"Archivo creado: {target}{suffix}"
        except (ValueError, OSError) as exc:
            return False, str(exc)
        finally:
            if staged and os.path.exists(staged):
                os.chmod(staged, 0o600)
                os.unlink(staged)

    def list_rule_files(self, sudoers_dir="/etc/sudoers.d") -> List[str]:
        directory = Path(sudoers_dir)
        if directory.is_symlink() or not directory.is_dir():
            return []
        return sorted(
            path.name
            for path in directory.iterdir()
            if re.fullmatch(r"[A-Za-z0-9_-]+", path.name)
            and path.is_file()
            and not path.is_symlink()
        )

    def remove_rule_file(
        self, file_name, sudoers_dir="/etc/sudoers.d"
    ) -> Tuple[bool, str]:
        try:
            target = self._target(file_name, sudoers_dir)
            if not target.exists():
                return False, f"Archivo no encontrado: {target}"
            if self.dry_run:
                return True, f"[DRY-RUN] Se eliminaría {target}"
            backup = self._backup(target)
            target.unlink()
            return True, f"Archivo eliminado: {target}; respaldo: {backup}"
        except (ValueError, OSError) as exc:
            return False, str(exc)

    def show_rule_file(
        self, file_name, sudoers_dir="/etc/sudoers.d"
    ) -> Tuple[bool, str]:
        try:
            target = self._target(file_name, sudoers_dir)
            if not target.exists():
                return False, f"Archivo no encontrado: {target}"
            return True, target.read_text(encoding="utf-8")
        except (ValueError, OSError) as exc:
            return False, str(exc)

    def validate_content(self, content, visudo_path="visudo") -> Tuple[bool, str]:
        path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, encoding="utf-8"
            ) as stream:
                stream.write(content)
                path = stream.name
            return self._validate_file(path, visudo_path)
        except OSError as exc:
            return False, str(exc)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def _build_file_content(rule):
        return (
            "# Managed by tools-admin (LDAP sudoers helper)\n" + rule.to_line() + "\n"
        )
