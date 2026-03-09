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
from .sudoers_manager import SudoersManager, SudoersRule

__all__ = [
    "LDAPClientInstaller",
    "LDAPConfig",
    "PAMConfig",
    "InstallationResult",
    "InstallationMode",
    "SudoersManager",
    "SudoersRule",
]
