"""Authoritative public-key inventory and synchronization for the login account.

Private keys never enter the payload. The remote Python helper only manages
~/.ssh/authorized_keys, preserving unrelated lines and existing key options.
"""

import base64
import hashlib
import json
import re
import shlex
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublicKey:
    line: str
    fingerprint: str


def validate_public_key(path):
    """Accept exactly one plain OpenSSH public key, verified by ssh-keygen."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if any(c in text for c in "\r\n\0"):
        raise ValueError("Expected one public key per file; never supply a private key")
    fields = text.split(None, 2)
    if len(fields) < 2 or not re.fullmatch(r"(?:ssh-|ecdsa-|sk-)[A-Za-z0-9@._+-]+", fields[0]):
        raise ValueError("Expected a plain OpenSSH public key without authorized_keys options")
    try:
        blob = base64.b64decode(fields[1], validate=True)
        size = struct.unpack(">I", blob[:4])[0]
        if blob[4:4 + size].decode("ascii") != fields[0]:
            raise ValueError("Key type does not match its payload")
    except (ValueError, UnicodeError, struct.error) as exc:
        raise ValueError("Invalid public key payload") from exc
    with tempfile.TemporaryDirectory(prefix="tools-key-") as directory:
        candidate = Path(directory) / "key.pub"
        candidate.write_text(text + "\n", encoding="utf-8")
        result = subprocess.run(
            ["ssh-keygen", "-l", "-E", "sha256", "-f", str(candidate)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            raise ValueError("ssh-keygen rejected the public key")
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return PublicKey(text, "SHA256:" + digest)


def load_servers(path):
    """Load authoritative per-account keys with paths relative to the inventory."""
    path = Path(path)
    inventory = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict) or set(inventory) != {"keys", "servers"}:
        raise ValueError("Inventory requires keys and servers")
    sources, servers = inventory["keys"], inventory["servers"]
    if not isinstance(sources, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in sources.items()
    ):
        raise ValueError("keys must map names to public key files")
    validated = {name: validate_public_key(path.parent / value) for name, value in sources.items()}
    if not isinstance(servers, list) or not servers:
        raise ValueError("Inventory must be a nonempty JSON array")
    normalized = []
    for server in servers:
        if not isinstance(server, dict) or set(server) - {"host", "user", "port", "keys"}:
            raise ValueError("Each server accepts only host, user, port and keys")
        host, user, port = server.get("host", ""), server.get("user", ""), server.get("port", 22)
        if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:%_-]*", host):
            raise ValueError("Invalid SSH host")
        if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", user):
            raise ValueError("Each host needs an explicit valid login user")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid SSH port")
        names = server.get("keys")
        if not isinstance(names, list) or not all(isinstance(n, str) and n in validated for n in names):
            raise ValueError("Each account requires an explicit list of known key names")
        item = {"host": host, "user": user, "port": port,
                "keys": list({validated[n].fingerprint: validated[n] for n in names}.values())}
        if any((s["host"], s["user"], s["port"]) == (host, user, port) for s in normalized):
            raise ValueError("Duplicate account in inventory")
        normalized.append(item)
    return normalized


# Executed by python3 on the remote host, or against disposable homes in tests.
REMOTE_HELPER = r'''
import base64, fcntl, hashlib, json, os, pathlib, shlex, stat, tempfile

def check(path, directory=False):
    if path.is_symlink():
        raise ValueError("Refusing symbolic link: " + str(path))
    if path.exists():
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("Unsafe owner or writable permissions: " + str(path))
        if directory != stat.S_ISDIR(info.st_mode) or (not directory and not stat.S_ISREG(info.st_mode)):
            raise ValueError("Unexpected file type: " + str(path))

def manage(home, keys, apply=False, allow_empty=False):
    if apply and not keys and not allow_empty:
        raise ValueError("Empty key list requires --allow-empty")
    home = pathlib.Path(home)
    check(home, True)
    directory = home / ".ssh"
    target = directory / "authorized_keys"
    check(directory, True)
    check(target)
    lock = None
    staged = None
    try:
        if apply:
            directory.mkdir(mode=0o700, exist_ok=True)
            lockpath = directory / ".tools-keys.lock"
            fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            lock = os.fdopen(fd, "a")
            if os.fstat(fd).st_uid != os.getuid() or not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Unsafe lock file")
            fcntl.flock(lock, fcntl.LOCK_EX)
            check(target)
        original = target.read_bytes() if target.exists() else b""
        existing = set()
        desired = {tuple(key.split()[:2]) for key in keys}
        retained = []
        removed = 0
        revoked = []
        for line in original.decode("utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                retained.append(line)
                continue
            try:
                tokens = shlex.split(line, comments=False)
            except ValueError:
                raise ValueError("Malformed authorized_keys line; manual review required")
            for i, token in enumerate(tokens[:-1]):
                if token.startswith(("ssh-", "ecdsa-", "sk-")):
                    identity = (token, tokens[i + 1])
                    if identity in desired:
                        retained.append(line)
                        existing.add(identity)
                    else:
                        removed += 1
                        try:
                            digest = hashlib.sha256(base64.b64decode(identity[1], validate=True)).digest()
                            revoked.append("SHA256:" + base64.b64encode(digest).decode().rstrip("="))
                        except ValueError:
                            raise ValueError("Malformed public key in authorized_keys; review required")
                    break
            else:
                raise ValueError("Unrecognized authorized_keys line; manual review required")
        missing = [key for key in keys if tuple(key.split()[:2]) not in existing]
        report = {"missing": len(missing), "extra": removed, "changed": False, "backup": None,
                  "revoked_fingerprints": revoked,
                  "path": str(target), "status": "drift" if missing or removed else "present"}
        if apply and (missing or removed):
            content = ("\n".join(retained + missing) + "\n").encode("utf-8")
            if target.exists():
                fd, backup = tempfile.mkstemp(prefix="authorized_keys.tools-backup-", dir=directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                report["backup"] = backup
            fd, staged = tempfile.mkstemp(prefix=".tools-keys-", dir=directory)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, target)
            staged = None
            if target.read_bytes() != content:
                raise ValueError("Post-write verification failed; inspect backup")
            report.update(changed=True, status="updated")
        return report
    finally:
        if staged and os.path.exists(staged):
            os.unlink(staged)
        if lock:
            lock.close()
'''


def inspect_server(server, keys, identity=None, apply=False, timeout=30, allow_empty=False):
    """Reconcile keys via noninteractive, host-verified SSH. Return per-host evidence."""
    payload = base64.b64encode(json.dumps({
        "keys": [k.line for k in keys], "apply": apply, "allow_empty": allow_empty,
    }).encode()).decode()
    script = REMOTE_HELPER + (
        "\npayload = json.loads(base64.b64decode('" + payload + "'))\n"
        "print(json.dumps(manage(pathlib.Path.home(), **payload)))\n"
    )
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", f"ConnectTimeout={timeout}", "-p", str(server["port"]), "-l", server["user"]]
    if identity:
        command += ["-i", str(identity), "-o", "IdentitiesOnly=yes"]
    command += ["--", server["host"], "python3 -c " + shlex.quote(script)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            return dict(server, success=False, error=result.stderr.strip() or "SSH helper failed")
        return dict(server, success=True, **json.loads(result.stdout))
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
        return dict(server, success=False, error=str(exc))
