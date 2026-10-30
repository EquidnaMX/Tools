"""Standalone PAM updater embedded in reviewed LDAP installation scripts.

The calling script backs up both services and restores them on any failure.
This module changes authentication only; account/session rules are preserved.
"""

import os
from pathlib import Path
import re
import tempfile


def configure_services(pam_dir, key_path):
    """Preflight both independent services, then install one rule in each."""
    directory = Path(pam_dir)
    if directory.is_symlink():
        raise ValueError("Refusing a symbolic-link PAM directory")
    line = f"auth sufficient pam_ssh_agent_auth.so file={key_path}\n"
    module = re.compile(r"^\s*auth\s+.*\bpam_ssh_agent_auth\.so(?:\s|$)")
    updates = []
    for service in ("sudo", "sudo-i"):
        path = directory / service
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"A regular PAM service file is required: {path}")
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        for existing in lines:
            if module.match(existing) and existing.strip() != line.strip():
                raise ValueError(f"Review the existing agent-auth rule in {path}")
        # Canonicalize our rule before auth includes; retain all unrelated checks.
        remaining = [item for item in lines if item.strip() != line.strip()]
        index = 1 if remaining and remaining[0].startswith("#%PAM-1.0") else 0
        if index and not remaining[0].endswith("\n"):
            remaining[0] += "\n"
        remaining.insert(index, line)
        proposed = "".join(remaining)
        if proposed != content:
            updates.append((path, proposed, path.stat()))
    for path, content, metadata in updates:
        fd, staged = tempfile.mkstemp(prefix=".tools-agent-", dir=str(directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), metadata.st_mode & 0o777)
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.replace(staged, path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)


if __name__ == "__main__":
    import sys

    user = sys.argv[1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", user):
        raise ValueError("Invalid sudo authentication user")
    configure_services("/etc/pam.d", f"/etc/security/authorized_keys_sudo_{user}")
