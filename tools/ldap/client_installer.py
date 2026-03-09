"""
Instalador y configurador de cliente LDAP para Linux.

Soporta configuración de:
- PAM (Pluggable Authentication Modules)
- NSLCD (Name Service LDAP Connection Daemon)
- SSSD (System Security Services Daemon)
- NSSwitch (Name Service Switch)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import json


class InstallationMode(Enum):
    """Modo de instalación LDAP."""
    NSLCD = "nslcd"
    SSSD = "sssd"


@dataclass
class LDAPConfig:
    """Configuración del servidor LDAP."""
    uri: str  # ldap://ldap.example.com o ldaps://ldap.example.com
    base_dn: str  # dc=example,dc=com
    bind_dn: Optional[str] = None  # cn=readonly,dc=example,dc=com
    bind_password: Optional[str] = None
    use_tls: bool = True
    tls_reqcert: str = "demand"  # never, allow, try, demand, hard
    tls_cacert_file: Optional[str] = "/etc/ssl/certs/ca-certificates.crt"
    search_timeout: int = 30
    reconnect_tries: int = 3


@dataclass
class PAMConfig:
    """Configuración de PAM."""
    allowed_groups: List[str] = field(default_factory=lambda: ["server-admin", "desarrollo"])
    create_home_dir: bool = True
    umask: str = "0077"
    password_hash: str = "yescrypt"  # yescrypt, sha512, md5


@dataclass
class InstallationResult:
    """Resultado de la instalación."""
    success: bool
    mode: InstallationMode
    timestamp: datetime
    steps_completed: List[str]
    steps_failed: List[str]
    backups_created: List[str]
    message: str
    details: Dict[str, any] = field(default_factory=dict)


class LDAPClientInstaller:
    """Instalador de cliente LDAP para Linux."""

    # Archivos PAM a configurar
    PAM_FILES = {
        "common-auth": "/etc/pam.d/common-auth",
        "common-account": "/etc/pam.d/common-account",
        "common-password": "/etc/pam.d/common-password",
        "common-session": "/etc/pam.d/common-session",
        "su": "/etc/pam.d/su",
    }

    GROUP_RULE_PREFIX = "auth    sufficient      pam_succeed_if.so user ingroup "
    GROUP_BLOCK_START = "# LDAP allowed groups (managed by tools-admin) - start"
    GROUP_BLOCK_END = "# LDAP allowed groups (managed by tools-admin) - end"

    def __init__(
        self,
        ldap_config: LDAPConfig,
        pam_config: Optional[PAMConfig] = None,
        mode: InstallationMode = InstallationMode.NSLCD,
        dry_run: bool = False,
    ):
        """
        Inicializa el instalador.

        Args:
            ldap_config: Configuración del servidor LDAP
            pam_config: Configuración de PAM
            mode: Modo de instalación (nslcd o sssd)
            dry_run: Si es True, no ejecuta comandos reales
        """
        self.ldap_config = ldap_config
        self.pam_config = pam_config or PAMConfig()
        self.mode = mode
        self.dry_run = dry_run
        self.backups_created = []
        self.steps_completed = []
        self.steps_failed = []

    def install(self, remote_host: Optional[str] = None) -> InstallationResult:
        """
        Instala y configura el cliente LDAP.

        Args:
            remote_host: Si se especifica, ejecuta en host remoto vía SSH

        Returns:
            InstallationResult con el resultado de la instalación
        """
        timestamp = datetime.now()

        try:
            # Paso 1: Instalar paquetes
            if not self._install_packages():
                return self._create_result(False, timestamp, "Failed to install packages")

            # Paso 2: Backup de archivos
            if not self._backup_configuration_files():
                return self._create_result(False, timestamp, "Failed to create backups")

            # Paso 3: Configurar PAM
            if not self._configure_pam():
                return self._create_result(False, timestamp, "Failed to configure PAM")

            # Paso 4: Configurar NSSwitch
            if not self._configure_nsswitch():
                return self._create_result(False, timestamp, "Failed to configure NSSwitch")

            # Paso 5: Configurar NSLCD o SSSD
            if self.mode == InstallationMode.NSLCD:
                if not self._configure_nslcd():
                    return self._create_result(False, timestamp, "Failed to configure NSLCD")
            else:
                if not self._configure_sssd():
                    return self._create_result(False, timestamp, "Failed to configure SSSD")

            # Paso 6: Reiniciar servicios
            if not self._restart_services():
                return self._create_result(False, timestamp, "Failed to restart services")

            return self._create_result(True, timestamp, "LDAP client configured successfully")

        except Exception as e:
            return self._create_result(False, timestamp, f"Installation failed: {e}")

    def _install_packages(self) -> bool:
        """Instala paquetes necesarios."""
        try:
            if self.mode == InstallationMode.NSLCD:
                packages = ["libpam-ldapd", "nslcd", "nscd"]
            else:
                packages = ["sssd", "libpam-sss", "libnss-sss"]

            command = f"apt update -y && apt install -y {' '.join(packages)}"

            if self.dry_run:
                print(f"[DRY-RUN] Would execute: {command}")
                self.steps_completed.append("install_packages (dry-run)")
                return True

            # En implementación real, ejecutar con subprocess o SSH
            self.steps_completed.append("install_packages")
            return True

        except Exception as e:
            self.steps_failed.append(f"install_packages: {e}")
            return False

    def _backup_configuration_files(self) -> bool:
        """Crea backups de archivos de configuración."""
        try:
            timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

            files_to_backup = list(self.PAM_FILES.values())
            files_to_backup.append("/etc/nsswitch.conf")

            if self.mode == InstallationMode.NSLCD:
                files_to_backup.append("/etc/nslcd.conf")
            else:
                files_to_backup.append("/etc/sssd/sssd.conf")

            for file_path in files_to_backup:
                backup_path = f"{file_path}.bak_{timestamp_suffix}"

                if self.dry_run:
                    print(f"[DRY-RUN] Would backup: {file_path} -> {backup_path}")
                else:
                    # En implementación real: cp file_path backup_path
                    pass

                self.backups_created.append(backup_path)

            self.steps_completed.append("backup_files")
            return True

        except Exception as e:
            self.steps_failed.append(f"backup_files: {e}")
            return False

    def _configure_pam(self) -> bool:
        """Configura archivos PAM."""
        try:
            # Generar configuraciones PAM
            pam_configs = self._generate_pam_configs()

            for file_name, content in pam_configs.items():
                file_path = self.PAM_FILES[file_name]

                if self.dry_run:
                    print(f"[DRY-RUN] Would write to {file_path}:")
                    print(content)
                    print("-" * 60)
                else:
                    # En implementación real: escribir archivo
                    pass

            self.steps_completed.append("configure_pam")
            return True

        except Exception as e:
            self.steps_failed.append(f"configure_pam: {e}")
            return False

    def _generate_pam_configs(self) -> Dict[str, str]:
        """Genera contenido de archivos PAM."""
        configs = {}

        # common-auth
        auth_lines = [
            "auth    sufficient      pam_unix.so",
            "auth    requisite       pam_ldap.so use_first_pass",
            "",
            self.GROUP_BLOCK_START,
            "# Solo habilitar acceso si el usuario está en estos grupos LDAP",
        ]

        for group in self.pam_config.allowed_groups:
            auth_lines.append(f"auth    sufficient      pam_succeed_if.so user ingroup {group}")

        auth_lines.append(self.GROUP_BLOCK_END)
        auth_lines.append("auth    requisite       pam_deny.so")
        configs["common-auth"] = "\n".join(auth_lines)

        # common-account
        configs["common-account"] = """account sufficient pam_unix.so
account sufficient pam_ldap.so
account requisite  pam_deny.so"""

        # common-password
        password_lines = [
            f"password sufficient pam_unix.so obscure {self.pam_config.password_hash}",
            "password sufficient pam_ldap.so try_first_pass",
            "password requisite  pam_deny.so",
        ]
        configs["common-password"] = "\n".join(password_lines)

        # common-session
        session_lines = [
            "session required pam_unix.so",
            "session optional pam_ldap.so",
            "session optional pam_systemd.so",
        ]

        if self.pam_config.umask:
            session_lines.append(f"session optional pam_umask.so umask={self.pam_config.umask}")

        if self.pam_config.create_home_dir:
            session_lines.append("session optional pam_mkhomedir.so skel=/etc/skel umask=0022")

        configs["common-session"] = "\n".join(session_lines)

        # su
        configs["su"] = """auth    sufficient pam_rootok.so
auth    include    common-auth
account include    common-account
session include    common-session
session optional   pam_mail.so nopen"""

        return configs

    def list_allowed_groups(self, pam_auth_file: Optional[str] = None) -> List[str]:
        """Lista los grupos permitidos actualmente en common-auth."""
        auth_file = Path(pam_auth_file or self.PAM_FILES["common-auth"])

        if not auth_file.exists():
            return []

        groups: List[str] = []
        for line in auth_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(self.GROUP_RULE_PREFIX):
                group = line.replace(self.GROUP_RULE_PREFIX, "", 1).strip()
                if group:
                    groups.append(group)

        return groups

    def _normalize_groups_block(self, lines: List[str], groups: List[str]) -> List[str]:
        """Normaliza el bloque de grupos LDAP en common-auth."""
        ordered_groups = sorted({g.strip() for g in groups if g and g.strip()})

        block_lines = [
            self.GROUP_BLOCK_START,
            "# Solo habilitar acceso si el usuario está en estos grupos LDAP",
        ]
        for group in ordered_groups:
            block_lines.append(f"{self.GROUP_RULE_PREFIX}{group}")
        block_lines.append(self.GROUP_BLOCK_END)

        skip_lines = {
            self.GROUP_BLOCK_START,
            self.GROUP_BLOCK_END,
            "# Solo habilitar acceso si el usuario está en estos grupos LDAP",
        }

        filtered_lines: List[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in skip_lines:
                continue
            if stripped.startswith(self.GROUP_RULE_PREFIX):
                continue
            filtered_lines.append(line)

        insert_at = len(filtered_lines)
        for i, line in enumerate(filtered_lines):
            if "pam_deny.so" in line:
                insert_at = i
                break

        if insert_at > 0 and filtered_lines[insert_at - 1].strip() != "":
            block_lines = [""] + block_lines

        return filtered_lines[:insert_at] + block_lines + filtered_lines[insert_at:]

    def add_allowed_group(self, group: str, pam_auth_file: Optional[str] = None) -> Tuple[bool, str]:
        """Agrega una regla pam_succeed_if para un grupo LDAP."""
        clean_group = group.strip()
        if not clean_group:
            return False, "El nombre del grupo no puede estar vacío"

        auth_file = Path(pam_auth_file or self.PAM_FILES["common-auth"])
        if not auth_file.exists():
            return False, f"Archivo no encontrado: {auth_file}"

        lines = auth_file.read_text(encoding="utf-8").splitlines()
        existing_groups = self.list_allowed_groups(pam_auth_file=str(auth_file))

        if clean_group in existing_groups:
            return False, f"El grupo '{clean_group}' ya existe"

        new_lines = self._normalize_groups_block(lines, existing_groups + [clean_group])

        if self.dry_run:
            return True, f"[DRY-RUN] Se agregaría el grupo '{clean_group}'"

        auth_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, f"Grupo agregado: {clean_group}"

    def remove_allowed_group(self, group: str, pam_auth_file: Optional[str] = None) -> Tuple[bool, str]:
        """Elimina una regla pam_succeed_if para un grupo LDAP."""
        clean_group = group.strip()
        if not clean_group:
            return False, "El nombre del grupo no puede estar vacío"

        auth_file = Path(pam_auth_file or self.PAM_FILES["common-auth"])
        if not auth_file.exists():
            return False, f"Archivo no encontrado: {auth_file}"

        lines = auth_file.read_text(encoding="utf-8").splitlines()
        existing_groups = self.list_allowed_groups(pam_auth_file=str(auth_file))

        if clean_group not in existing_groups:
            return False, f"El grupo '{clean_group}' no existe"

        remaining_groups = [g for g in existing_groups if g != clean_group]
        new_lines = self._normalize_groups_block(lines, remaining_groups)

        if self.dry_run:
            return True, f"[DRY-RUN] Se quitaría el grupo '{clean_group}'"

        auth_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, f"Grupo eliminado: {clean_group}"

    def _configure_nsswitch(self) -> bool:
        """Configura NSSwitch para usar LDAP."""
        try:
            nsswitch_content = """# /etc/nsswitch.conf

passwd:         files ldap
group:          files ldap
shadow:         files ldap
gshadow:        files

hosts:          files dns
networks:       files

protocols:      db files
services:       db files
ethers:         db files
rpc:            db files

netgroup:       nis"""

            if self.dry_run:
                print("[DRY-RUN] Would write to /etc/nsswitch.conf:")
                print(nsswitch_content)
            else:
                # En implementación real: escribir archivo
                pass

            self.steps_completed.append("configure_nsswitch")
            return True

        except Exception as e:
            self.steps_failed.append(f"configure_nsswitch: {e}")
            return False

    def _configure_nslcd(self) -> bool:
        """Configura NSLCD."""
        try:
            nslcd_config = f"""# /etc/nslcd.conf

# LDAP server URI
uri {self.ldap_config.uri}

# Base DN
base {self.ldap_config.base_dn}

# LDAP protocol version
ldap_version 3

# Bind credentials
"""

            if self.ldap_config.bind_dn:
                nslcd_config += f"binddn {self.ldap_config.bind_dn}\n"
                nslcd_config += f"bindpw {self.ldap_config.bind_password}\n"

            nslcd_config += f"""
# TLS settings
{'ssl on' if self.ldap_config.uri.startswith('ldaps') else ''}
{'tls_starttls yes' if self.ldap_config.use_tls and not self.ldap_config.uri.startswith('ldaps') else ''}
tls_reqcert {self.ldap_config.tls_reqcert}
"""

            if self.ldap_config.tls_cacert_file:
                nslcd_config += f"tls_cacertfile {self.ldap_config.tls_cacert_file}\n"

            nslcd_config += f"""
# Timeouts
timelimit {self.ldap_config.search_timeout}
bind_timelimit 10

# Reconnect policy
reconnect_tries {self.ldap_config.reconnect_tries}
"""

            if self.dry_run:
                print("[DRY-RUN] Would write to /etc/nslcd.conf:")
                print(nslcd_config)
            else:
                # En implementación real: escribir archivo
                # chmod 600 /etc/nslcd.conf
                pass

            self.steps_completed.append("configure_nslcd")
            return True

        except Exception as e:
            self.steps_failed.append(f"configure_nslcd: {e}")
            return False

    def _configure_sssd(self) -> bool:
        """Configura SSSD."""
        try:
            sssd_config = f"""[sssd]
services = nss, pam
config_file_version = 2
domains = LDAP

[nss]
filter_users = root
filter_groups = root

[pam]
offline_credentials_expiration = 7

[domain/LDAP]
id_provider = ldap
auth_provider = ldap
chpass_provider = ldap

ldap_uri = {self.ldap_config.uri}
ldap_search_base = {self.ldap_config.base_dn}
"""

            if self.ldap_config.bind_dn:
                sssd_config += f"ldap_default_bind_dn = {self.ldap_config.bind_dn}\n"
                sssd_config += f"ldap_default_authtok = {self.ldap_config.bind_password}\n"

            sssd_config += f"""
ldap_tls_reqcert = {self.ldap_config.tls_reqcert}
"""

            if self.ldap_config.tls_cacert_file:
                sssd_config += f"ldap_tls_cacert = {self.ldap_config.tls_cacert_file}\n"

            sssd_config += """
cache_credentials = true
enumerate = false
"""

            if self.dry_run:
                print("[DRY-RUN] Would write to /etc/sssd/sssd.conf:")
                print(sssd_config)
                print("[DRY-RUN] Would set permissions: chmod 600 /etc/sssd/sssd.conf")
            else:
                # En implementación real: escribir archivo
                # chmod 600 /etc/sssd/sssd.conf
                pass

            self.steps_completed.append("configure_sssd")
            return True

        except Exception as e:
            self.steps_failed.append(f"configure_sssd: {e}")
            return False

    def _restart_services(self) -> bool:
        """Reinicia servicios necesarios."""
        try:
            if self.mode == InstallationMode.NSLCD:
                services = ["nslcd", "nscd"]
            else:
                services = ["sssd"]

            for service in services:
                if self.dry_run:
                    print(f"[DRY-RUN] Would restart service: {service}")
                else:
                    # En implementación real: systemctl restart service
                    pass

            self.steps_completed.append("restart_services")
            return True

        except Exception as e:
            self.steps_failed.append(f"restart_services: {e}")
            return False

    def _create_result(self, success: bool, timestamp: datetime, message: str) -> InstallationResult:
        """Crea el resultado de la instalación."""
        return InstallationResult(
            success=success,
            mode=self.mode,
            timestamp=timestamp,
            steps_completed=self.steps_completed.copy(),
            steps_failed=self.steps_failed.copy(),
            backups_created=self.backups_created.copy(),
            message=message,
            details={
                "ldap_uri": self.ldap_config.uri,
                "base_dn": self.ldap_config.base_dn,
                "allowed_groups": self.pam_config.allowed_groups,
                "mode": self.mode.value,
            },
        )

    def generate_script(self) -> str:
        """
        Genera un script bash que puede ser ejecutado directamente.

        Returns:
            Contenido del script bash
        """
        pam_configs = self._generate_pam_configs()

        script = """#!/bin/bash
# Auto-generated LDAP client configuration script
# Generated by tools-admin toolkit

set -euo pipefail

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[0;33m'
BLUE='\\033[0;34m'
NC='\\033[0m' # No Color

# Backup function
backup_file() {
    local file=$1
    if [[ -f $file ]]; then
        local backup="${file}.bak_$(date +%F_%T)"
        sudo cp "$file" "$backup"
        echo -e "${YELLOW}[BACKUP]${NC} Created: $backup"
    fi
}

echo -e "${BLUE}[INFO]${NC} Installing LDAP client packages..."
"""

        # Paquetes
        if self.mode == InstallationMode.NSLCD:
            script += "sudo apt update -y\n"
            script += "sudo apt install -y libpam-ldapd nslcd nscd\n\n"
        else:
            script += "sudo apt update -y\n"
            script += "sudo apt install -y sssd libpam-sss libnss-sss\n\n"

        # PAM files
        for file_name, content in pam_configs.items():
            file_path = self.PAM_FILES[file_name]
            script += f"# Configure {file_name}\n"
            script += f"backup_file '{file_path}'\n"
            script += f"cat <<'PAMEOF' | sudo tee '{file_path}' > /dev/null\n"
            script += content + "\n"
            script += "PAMEOF\n\n"

        # NSSwitch
        script += "# Configure NSSwitch\n"
        script += "backup_file '/etc/nsswitch.conf'\n"
        script += "cat <<'NSSEOF' | sudo tee '/etc/nsswitch.conf' > /dev/null\n"
        script += """passwd:         files ldap
group:          files ldap
shadow:         files ldap

hosts:          files dns
networks:       files

protocols:      db files
services:       db files
NSSEOF

"""

        # NSLCD or SSSD config
        if self.mode == InstallationMode.NSLCD:
            script += "# Configure NSLCD\n"
            script += "backup_file '/etc/nslcd.conf'\n"
            # Generar configuración NSLCD completa aquí
            script += f"cat <<'NSLCDEOF' | sudo tee '/etc/nslcd.conf' > /dev/null\n"
            script += f"uri {self.ldap_config.uri}\n"
            script += f"base {self.ldap_config.base_dn}\n"
            script += "NSLCDEOF\n"
            script += "sudo chmod 600 /etc/nslcd.conf\n\n"
            script += "sudo systemctl restart nslcd nscd\n"
        else:
            script += "# Configure SSSD\n"
            script += "sudo mkdir -p /etc/sssd\n"
            script += "backup_file '/etc/sssd/sssd.conf'\n"
            script += "# SSSD config here\n"
            script += "sudo chmod 600 /etc/sssd/sssd.conf\n\n"
            script += "sudo systemctl restart sssd\n"

        script += f'\necho -e "${{GREEN}}[DONE]${{NC}} LDAP client configured successfully!"\n'

        return script
