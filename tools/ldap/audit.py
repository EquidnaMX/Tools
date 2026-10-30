"""Read-only LDAP/PAM/SSH configuration inspection. Never return file contents."""

import configparser
import re
import shlex
from pathlib import Path

from tools.ldap.connection import validate_endpoint


def audit_client(root="/"):
    """Report static evidence; includes and running services need separate verification."""
    root = Path(root)
    checks = []

    def record(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    def read(relative):
        path = root / relative
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    backends = []
    for mode, relative in [("nslcd", "etc/nslcd.conf"), ("sssd", "etc/sssd/sssd.conf")]:
        try:
            text = read(relative)
            if text is None:
                continue
            backends.append(mode)
            if mode == "nslcd":
                values = {}
                for line in text.splitlines():
                    parts = shlex.split(line, comments=True)
                    if len(parts) >= 2:
                        values[parts[0].lower()] = " ".join(parts[1:])
                domains = [(mode, values.get("uri", ""), values.get("ssl") in ("on", "start_tls"),
                            values.get("tls_reqcert", "demand"), values.get("tls_cacertfile"))]
            else:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(text)
                domains = [(section, parser.get(section, "ldap_uri", fallback=""),
                            parser.getboolean(section, "ldap_id_use_start_tls", fallback=False),
                            parser.get(section, "ldap_tls_reqcert", fallback="hard"),
                            parser.get(section, "ldap_tls_cacert", fallback=None))
                           for section in parser.sections() if section.startswith("domain/")]
            if not domains:
                record(mode, "fail", "No hay un dominio LDAP definido")
            for domain, uris, tls, policy, ca in domains:
                endpoints = [validate_endpoint(uri) for uri in uris.split()]
                encrypted = bool(endpoints) and all(uri.scheme == "ldaps" or tls for uri in endpoints)
                record(domain + ":tls", "pass" if encrypted else "fail",
                       "Transporte cifrado configurado" if encrypted else
                       "TLS no está configurado para todos los destinos")
                record(domain + ":certificates", "pass" if policy in ("demand", "hard") else "fail",
                       "Verificación de certificado: " + policy)
                if ca:
                    exists = Path(ca).is_absolute() and (root / ca.lstrip("/")).is_file()
                    record(domain + ":ca", "pass" if exists else "fail", "Comprobar archivo CA configurado")
                else:
                    record(domain + ":ca", "review", "Confirmar almacén CA efectivo del sistema")
        except (OSError, ValueError, configparser.Error):
            record(mode, "fail", "Configuración ilegible o inválida; revisar localmente sin publicar credenciales")
    record("backend", "pass" if len(backends) == 1 else "review" if backends else "fail",
           "Detectados: " + (", ".join(backends) or "ninguno"))
    try:
        account = read("etc/pam.d/common-account") or ""
        marker = "# LDAP allowed groups (managed by tools-admin) - start"
        record("pam:groups", "review", "Revisar política de cuenta" + (
            " gestionada por Tools" if marker in account else " existente"))
        for mode, module in [("nslcd", "pam_ldap.so"), ("sssd", "pam_sss.so")]:
            if mode in backends:
                active = "\n".join(line for line in account.splitlines() if not line.lstrip().startswith("#"))
                record("pam:" + mode, "pass" if module in active else "review",
                       "Buscar módulo en common-account; verificar también inclusiones y common-auth")
        ssh = read("etc/ssh/sshd_config") or ""
        explicit_no = re.search(r"(?im)^\s*UsePAM\s+no\s*(?:#.*)?$", ssh)
        record("ssh:pam", "fail" if explicit_no else "review",
               "UsePAM no detectado" if explicit_no else "Confirmar UsePAM efectivo con sshd -T y los criterios Match")
    except OSError:
        record("pam:ssh", "fail", "No se pudieron leer las configuraciones PAM/SSH")
    return {"checks": checks, "success": not any(c["status"] == "fail" for c in checks),
            "scope": "Inspección estática; no prueba servicios, certificados, NSS ni acceso SSH real"}
