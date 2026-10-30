"""LDAP configuration plans and account-phase group authorization.

Direct privileged application is deliberately unsupported. Generate a reviewed
standalone script or preview a plan; neither path silently applies to a host.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional
import os
import inspect
import re
import shlex
import tempfile

from tools.ldap.connection import validate_endpoint
from tools.ldap import ssh_agent_sudo
from tools.remote.ssh_keys import validate_public_key


class InstallationMode(Enum):
    NSLCD = "nslcd"
    SSSD = "sssd"


@dataclass
class LDAPConfig:
    uri: str
    base_dn: str
    bind_dn: Optional[str] = None
    bind_password: Optional[str] = field(default=None, repr=False)
    use_tls: bool = True
    tls_reqcert: str = "demand"
    tls_cacert_file: Optional[str] = "/etc/ssl/certs/ca-certificates.crt"
    search_timeout: int = 30
    reconnect_tries: int = 3


@dataclass
class PAMConfig:
    allowed_groups: List[str] = field(
        default_factory=lambda: ["server-admin", "desarrollo"]
    )
    create_home_dir: bool = True
    umask: str = "0077"
    password_hash: str = "yescrypt"


@dataclass
class InstallationResult:
    success: bool
    mode: InstallationMode
    timestamp: datetime
    steps_completed: List[str]
    steps_failed: List[str]
    backups_created: List[str]
    message: str
    details: Dict[str, object] = field(default_factory=dict)


class LDAPClientInstaller:
    PAM_FILES = {
        "common-auth": "/etc/pam.d/common-auth",
        "common-account": "/etc/pam.d/common-account",
        "common-password": "/etc/pam.d/common-password",
        "common-session": "/etc/pam.d/common-session",
        "su": "/etc/pam.d/su",
    }
    GROUP_BLOCK_START = "# LDAP allowed groups (managed by tools-admin) - start"
    GROUP_BLOCK_END = "# LDAP allowed groups (managed by tools-admin) - end"
    GROUP_RULE_PREFIX = "account requisite pam_succeed_if.so user ingroup "
    GROUP_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")

    def __init__(
        self, ldap_config, pam_config=None, mode=InstallationMode.NSLCD, dry_run=False,
        ssh_sudo_user=None, ssh_sudo_public_key=None,
    ):
        self.ldap_config = ldap_config
        self.pam_config = pam_config or PAMConfig()
        self.mode = mode
        self.dry_run = dry_run
        self.ssh_sudo_user = ssh_sudo_user
        self.ssh_sudo_public_key = ssh_sudo_public_key
        self.backups_created = []
        self.steps_completed = []
        self.steps_failed = []

    def _validate(self):
        if self.ssh_sudo_user is not None or self.ssh_sudo_public_key is not None:
            if not self.ssh_sudo_user or not self.ssh_sudo_public_key:
                raise ValueError("Specify both ssh_sudo_user and ssh_sudo_public_key")
            if not isinstance(self.ssh_sudo_user, str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_-]*", self.ssh_sudo_user
            ):
                raise ValueError("Invalid sudo authentication user")
        if not isinstance(self.mode, InstallationMode):
            raise ValueError("Unsupported LDAP mode")
        cfg = self.ldap_config
        for name in ("uri", "base_dn", "bind_dn", "bind_password", "tls_cacert_file"):
            value = getattr(cfg, name)
            if value is not None and (
                not isinstance(value, str) or any(c in value for c in "\r\n\0")
            ):
                raise ValueError(f"{name} must be a single configuration value")
        validate_endpoint(cfg.uri)
        if not cfg.base_dn.strip():
            raise ValueError("An LDAP URI and nonempty base DN are required")
        if cfg.bind_dn and not cfg.bind_password:
            raise ValueError("bind_password is required with bind_dn")
        if cfg.bind_password and not cfg.bind_dn:
            raise ValueError("bind_dn is required with bind_password")
        if cfg.bind_dn and cfg.uri.startswith("ldap://") and not cfg.use_tls:
            raise ValueError("Refusing a password bind over unencrypted LDAP")
        if cfg.tls_reqcert not in ("never", "allow", "try", "demand", "hard"):
            raise ValueError("Unsupported TLS certificate policy")
        if cfg.search_timeout <= 0 or cfg.reconnect_tries <= 0:
            raise ValueError("Timeout and reconnect settings must be positive")
        if self.pam_config.password_hash not in ("yescrypt", "sha512", "sha256", "md5"):
            raise ValueError("Unsupported password hash")
        if not re.fullmatch(r"0?[0-7]{3}", self.pam_config.umask):
            raise ValueError("Invalid home-directory umask")
        for group in self.pam_config.allowed_groups:
            self._validate_group(group)

    @classmethod
    def _validate_group(cls, group):
        if not isinstance(group, str) or not cls.GROUP_NAME.fullmatch(group):
            raise ValueError(
                "Invalid group name (no PAM operators, whitespace or newlines)"
            )
        return group

    def install(self, remote_host=None):
        """Preview only; refuse unsupported local or remote execution explicitly."""
        self.steps_completed = []
        self.steps_failed = []
        self.backups_created = []
        timestamp = datetime.now()
        if remote_host:
            self.steps_failed.append("remote_execution_unsupported")
            return self._create_result(
                False,
                timestamp,
                "Remote installation is unsupported; generate a script",
            )
        if not self.dry_run:
            self.steps_failed.append("direct_execution_unsupported")
            return self._create_result(
                False,
                timestamp,
                "Direct installation is unsupported; use --dry-run or --output-script",
            )
        try:
            self._validate()
            configs = self._configuration_files(redact=True)
            print("[DRY-RUN] Packages: " + " ".join(self._packages()))
            for path, (content, _) in configs.items():
                print(f"[DRY-RUN] Would back up and write {path}:\n{content}")
            if self.ssh_sudo_user:
                print("[DRY-RUN] Would back up and preserve/update both "
                      "/etc/pam.d/sudo and /etc/pam.d/sudo-i for SSH agent authentication")
            self.steps_completed = ["validate_plan", "render_configuration (dry-run)"]
            return self._create_result(
                True,
                timestamp,
                "Plan generated; no files, packages or services changed",
            )
        except (ValueError, TypeError) as exc:
            self.steps_failed.append("invalid_configuration")
            return self._create_result(False, timestamp, str(exc))

    def _create_result(self, success, timestamp, message):
        return InstallationResult(
            success,
            self.mode,
            timestamp,
            self.steps_completed.copy(),
            self.steps_failed.copy(),
            self.backups_created.copy(),
            message,
            {
                "ldap_uri": self.ldap_config.uri,
                "base_dn": self.ldap_config.base_dn,
                "allowed_groups": self.pam_config.allowed_groups,
                "mode": self.mode.value,
            },
        )

    @classmethod
    def _group_block(cls, groups):
        groups = sorted({cls._validate_group(g) for g in groups})
        gate = (
            cls.GROUP_RULE_PREFIX + ":".join(groups)
            if groups
            else "account requisite pam_deny.so"
        )
        return [
            cls.GROUP_BLOCK_START,
            "# Local recovery users still undergo the remaining account checks.",
            "account [success=1 default=ignore] pam_localuser.so",
            gate,
            cls.GROUP_BLOCK_END,
        ]

    def _generate_pam_configs(self):
        self._validate()
        module = "pam_ldap.so" if self.mode == InstallationMode.NSLCD else "pam_sss.so"
        auth = [
            "auth [success=2 default=ignore] pam_unix.so",
            f"auth [success=1 default=ignore] {module} use_first_pass",
            "auth requisite pam_deny.so",
            "auth required pam_permit.so",
        ]
        account = self._group_block(self.pam_config.allowed_groups) + [
            "account [success=1 default=ignore] pam_localuser.so",
            f"account [success=1 new_authtok_reqd=done default=die] {module}",
            "account required pam_unix.so",
            "account required pam_permit.so",
        ]
        session = [
            "session required pam_unix.so",
            f"session optional {module}",
            "session optional pam_systemd.so",
            f"session optional pam_umask.so umask={self.pam_config.umask}",
        ]
        if self.pam_config.create_home_dir:
            session.append(
                f"session optional pam_mkhomedir.so skel=/etc/skel umask={self.pam_config.umask}"
            )
        return {
            "common-auth": "\n".join(auth),
            "common-account": "\n".join(account),
            "common-password": "\n".join(
                [
                    f"password [success=2 default=ignore] pam_unix.so obscure {self.pam_config.password_hash}",
                    f"password [success=1 default=ignore] {module} try_first_pass",
                    "password requisite pam_deny.so",
                    "password required pam_permit.so",
                ]
            ),
            "common-session": "\n".join(session),
            "su": (
                "auth sufficient pam_rootok.so\n@include common-auth\n"
                "@include common-account\n@include common-session"
            ),
        }

    @staticmethod
    def _account_path(pam_account_file=None, pam_auth_file=None):
        if pam_auth_file is not None:
            raise ValueError(
                "Group policy belongs in common-account; use pam_account_file / --pam-account-file"
            )
        path = Path(pam_account_file or "/etc/pam.d/common-account")
        if path.name == "common-auth" or path.is_symlink():
            raise ValueError(
                "Refusing to modify an auth stack or symbolic link; use common-account"
            )
        return path

    def list_allowed_groups(self, pam_account_file=None, *, pam_auth_file=None):
        path = self._account_path(pam_account_file, pam_auth_file)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        if self.GROUP_BLOCK_START not in lines:
            return []
        start = lines.index(self.GROUP_BLOCK_START)
        if any(self._is_account_boundary(line) for line in lines[:start]):
            raise ValueError(
                "Managed group policy must precede account rules and includes"
            )
        after_start = start + 1
        if self.GROUP_BLOCK_END not in lines[after_start:]:
            raise ValueError("Incomplete managed account block")
        end = lines.index(self.GROUP_BLOCK_END, after_start)
        groups = []
        for line in lines[after_start:end]:
            if line.startswith(self.GROUP_RULE_PREFIX):
                rule_start = len(self.GROUP_RULE_PREFIX)
                groups.extend(line[rule_start:].split(":"))
        return sorted({self._validate_group(g) for g in groups})

    def _normalize_groups_block(self, lines, groups):
        """Only replace our account block; never rearrange auth or numeric jumps."""
        if (
            lines.count(self.GROUP_BLOCK_START) != lines.count(self.GROUP_BLOCK_END)
            or lines.count(self.GROUP_BLOCK_START) > 1
        ):
            raise ValueError("Invalid managed account block")
        block = self._group_block(groups)
        if self.GROUP_BLOCK_START in lines:
            start, end = lines.index(self.GROUP_BLOCK_START), lines.index(
                self.GROUP_BLOCK_END
            )
            if end < start:
                raise ValueError("Invalid managed account block order")
            if any(self._is_account_boundary(line) for line in lines[:start]):
                raise ValueError(
                    "Managed group policy must precede account rules and includes"
                )
            after_end = end + 1
            return lines[:start] + block + lines[after_end:]
        # Insert before the first account rule, leaving auth jumps byte-for-byte in place.
        start = next(
            (i for i, line in enumerate(lines) if self._is_account_boundary(line)),
            len(lines),
        )
        return lines[:start] + block + lines[start:]

    @staticmethod
    def _is_account_boundary(line):
        return bool(re.match(r"^\s*(?:-?account\s|@include\s)", line))

    def _change_group(self, group, add, pam_account_file, pam_auth_file):
        try:
            group = self._validate_group(group)
            path = self._account_path(pam_account_file, pam_auth_file)
            if not path.is_file():
                return False, f"Archivo no encontrado: {path}"
            groups = self.list_allowed_groups(pam_account_file=str(path))
            if (group in groups) == add:
                return (
                    False,
                    f"El grupo '{group}' {'ya existe' if add else 'no existe'}",
                )
            groups = groups + [group] if add else [g for g in groups if g != group]
            content = path.read_text(encoding="utf-8")
            # Preserve the line endings and untouched stack, including a missing final newline.
            newline = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
            lines = self._normalize_groups_block(content.splitlines(), groups)
            updated = newline.join(lines) + (newline if content.endswith("\n") else "")
            if self.dry_run:
                return (
                    True,
                    f"[DRY-RUN] Se {'agregaría' if add else 'quitaría'} '{group}' en common-account",
                )
            mode = path.stat().st_mode & 0o777
            fd, staged = tempfile.mkstemp(
                prefix=".tools-account-", dir=str(path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                    stream.write(updated)
                os.chmod(staged, mode)
                if hasattr(os, "chown"):
                    os.chown(staged, path.stat().st_uid, path.stat().st_gid)
                os.replace(staged, path)
            finally:
                if os.path.exists(staged):
                    os.unlink(staged)
            return (
                True,
                f"Grupo {'agregado' if add else 'eliminado'} en common-account: {group}",
            )
        except (ValueError, OSError) as exc:
            return False, str(exc)

    def add_allowed_group(self, group, pam_account_file=None, *, pam_auth_file=None):
        return self._change_group(group, True, pam_account_file, pam_auth_file)

    def remove_allowed_group(self, group, pam_account_file=None, *, pam_auth_file=None):
        return self._change_group(group, False, pam_account_file, pam_auth_file)

    def _packages(self):
        packages = (
            ["libpam-ldapd", "libnss-ldapd", "nslcd", "nscd"]
            if self.mode == InstallationMode.NSLCD
            else ["sssd", "libpam-sss", "libnss-sss"]
        )
        if self.ssh_sudo_user:
            packages += ["libpam-ssh-agent-auth", "python3", "sudo"]
        return packages

    def _daemon_config(self, redact=False):
        self._validate()
        cfg = (
            replace(self.ldap_config, bind_password="<REDACTED>")
            if redact
            else self.ldap_config
        )
        start_tls = cfg.use_tls and not cfg.uri.startswith("ldaps://")
        if self.mode == InstallationMode.NSLCD:
            lines = ["uid nslcd", "gid nslcd", f"uri {cfg.uri}", f"base {cfg.base_dn}"]
            if cfg.bind_dn:
                # nslcd quoted tokens preserve whitespace, quotes and literal backslashes.
                def quote(v):
                    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

                lines += [
                    f"binddn {quote(cfg.bind_dn)}",
                    f"bindpw {quote(cfg.bind_password)}",
                ]
            lines += [
                "ssl "
                + (
                    "on"
                    if cfg.uri.startswith("ldaps://")
                    else "start_tls" if start_tls else "off"
                ),
                f"tls_reqcert {cfg.tls_reqcert}",
                f"timelimit {cfg.search_timeout}",
                "bind_timelimit 10",
            ]
            if cfg.tls_cacert_file:
                lines.append(f"tls_cacertfile {cfg.tls_cacert_file}")
        else:
            lines = [
                "[sssd]",
                "services = nss, pam",
                "config_file_version = 2",
                "domains = LDAP",
                "",
                "[nss]",
                "filter_users = root",
                "filter_groups = root",
                "",
                "[pam]",
                "",
                "[domain/LDAP]",
                "id_provider = ldap",
                "auth_provider = ldap",
                "chpass_provider = ldap",
                f"ldap_uri = {cfg.uri}",
                f"ldap_search_base = {cfg.base_dn}",
                f"ldap_id_use_start_tls = {str(start_tls).lower()}",
                f"ldap_tls_reqcert = {cfg.tls_reqcert}",
                "cache_credentials = true",
                "enumerate = false",
                f"ldap_network_timeout = {cfg.search_timeout}",
            ]
            if cfg.bind_dn:
                lines += [
                    f"ldap_default_bind_dn = {cfg.bind_dn}",
                    "ldap_default_authtok_type = password",
                    f"ldap_default_authtok = {cfg.bind_password}",
                ]
            if cfg.tls_cacert_file:
                lines.append(f"ldap_tls_cacert = {cfg.tls_cacert_file}")
        return "\n".join(lines) + "\n"

    def _configuration_files(self, redact=False):
        configs = {
            self.PAM_FILES[name]: (body + "\n", 0o644)
            for name, body in self._generate_pam_configs().items()
        }
        backend = "ldap" if self.mode == InstallationMode.NSLCD else "sss"
        nss = "\n".join(
            [
                f"passwd: files {backend}",
                f"group: files {backend}",
                f"shadow: files {backend}",
                "gshadow: files",
                "hosts: files dns",
                "networks: files",
                "protocols: db files",
                "services: db files",
                "ethers: db files",
                "rpc: db files",
                "netgroup: nis",
                "",
            ]
        )
        configs["/etc/nsswitch.conf"] = (nss, 0o644)
        daemon = (
            "/etc/nslcd.conf"
            if self.mode == InstallationMode.NSLCD
            else "/etc/sssd/sssd.conf"
        )
        configs[daemon] = (self._daemon_config(redact=redact), 0o600)
        if self.ssh_sudo_user:
            key = validate_public_key(self.ssh_sudo_public_key)
            user = self.ssh_sudo_user
            configs[f"/etc/security/authorized_keys_sudo_{user}"] = (key.line + "\n", 0o600)
            configs[f"/etc/sudoers.d/90-tools-ssh-agent-{user}"] = (
                f'Defaults:{user} env_keep += "SSH_AUTH_SOCK"\n', 0o440
            )
        return configs

    def generate_script(self):
        """Render one reviewed local-root script, including rollback of configuration."""
        self._validate()
        configs = self._configuration_files()
        script = r"""#!/bin/bash
# Generated configuration plan. Review before executing on a server.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Run this reviewed script as root" >&2; exit 1; }
umask 077
backup_dir=$(mktemp -d /var/backups/tools-ldap.XXXXXX)
touch "$backup_dir/manifest"
touch "$backup_dir/active-services"
staged=""
backup_file() {
    local target="$1" index="$2"
    [[ ! -L "$target" ]] || { echo "Refusing symlink: $target" >&2; exit 1; }
    if [[ -e "$target" ]]; then
        cp -p -- "$target" "$backup_dir/$index"
        printf 'yes\t%s\t%s\n' "$index" "$target" >> "$backup_dir/manifest"
    else
        printf 'no\t%s\t%s\n' "$index" "$target" >> "$backup_dir/manifest"
    fi
}
rollback() {
    trap - ERR INT TERM
    local existed index target
    [[ -z "$staged" ]] || rm -f -- "$staged"
    while IFS="$(printf '\t')" read -r existed index target; do
        if [[ $existed == yes ]]; then
            cp -p -- "$backup_dir/$index" "$target" || true
        else
            rm -f -- "$target"
        fi
    done < "$backup_dir/manifest"
    for service in __TOOLS_SERVICES__; do
        if grep -Fxq "$service" "$backup_dir/active-services"; then
            systemctl restart "$service" || true
        else
            systemctl stop "$service" || true
        fi
    done
    echo "Configuration restored; installed packages are not removed. Backup: $backup_dir" >&2
}
trap 'rollback' ERR
trap 'rollback; exit 130' INT
trap 'rollback; exit 143' TERM
"""
        services = "nslcd nscd" if self.mode == InstallationMode.NSLCD else "sssd"
        script = script.replace("__TOOLS_SERVICES__", services)
        if self.ssh_sudo_user:
            script = script.replace(
                'backup_dir=$(mktemp',
                'command -v visudo >/dev/null\nvisudo -c\nbackup_dir=$(mktemp',
                1,
            )
        for service in services.split():
            script += (
                f"if systemctl is-active --quiet {service}; then "
                f'echo {service} >> "$backup_dir/active-services"; fi\n'
            )
        for index, path in enumerate(configs):
            script += f"backup_file {shlex.quote(path)} {index}\n"
        if self.ssh_sudo_user:
            for index, service in enumerate(("sudo", "sudo-i"), start=len(configs)):
                path = f"/etc/pam.d/{service}"
                script += f'[[ -f {path} ]] || {{ echo "Missing PAM service: {path}" >&2; exit 1; }}\n'
                script += f"backup_file {path} {index}\n"
        script += "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade --no-install-recommends "
        script += " ".join(self._packages()) + "\n"
        for index, (path, (content, mode)) in enumerate(configs.items()):
            marker = f"TOOLS_CONFIG_{index}_EOF"
            if marker in content.splitlines():
                raise ValueError("Configuration contains a script delimiter")
            script += f"mkdir -p -- {shlex.quote(str(PurePosixPath(path).parent))}\n"
            script += f"staged=$(mktemp {shlex.quote(path + '.tools.XXXXXX')})\n"
            script += f"cat <<'{marker}' > \"$staged\"\n{content}{marker}\n"
            script += f'chmod {mode:o} "$staged"\nchown root:root "$staged"\n'
            if path.startswith("/etc/sudoers.d/"):
                script += 'visudo -cf "$staged"\n'
            script += f'mv -f -- "$staged" {shlex.quote(path)}\n'
        if self.ssh_sudo_user:
            source = inspect.getsource(ssh_agent_sudo)
            script += f"python3 - {shlex.quote(self.ssh_sudo_user)} <<'TOOLS_SUDO_PAM_EOF'\n"
            script += source + "\nTOOLS_SUDO_PAM_EOF\nvisudo -c\n"
        if self.mode == InstallationMode.SSSD:
            script += "if command -v sssctl >/dev/null; then sssctl config-check; fi\n"
        script += f"systemctl restart {services}\ntrap - ERR INT TERM\n"
        script += 'printf "Configuration applied. Backups: %s\\n" "$backup_dir"\n'
        return script
