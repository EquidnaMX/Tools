"""
Módulo de autenticación LDAP.

Proporciona capacidades para configurar clientes Linux para
autenticarse contra servidores LDAP remotos usando PAM y NSLCD/SSSD.
"""

from .client_installer import (
    LDAPClientInstaller,
    LDAPConfig,
    PAMConfig,
    InstallationResult,
    InstallationMode,
)

__all__ = [
    "LDAPClientInstaller",
    "LDAPConfig",
    "PAMConfig",
    "InstallationResult",
    "InstallationMode",
]
