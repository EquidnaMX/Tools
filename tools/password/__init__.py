"""
Tools password management module

Secure password management system with:
- Multi-host SSH-based password changes
- LDAP directory synchronization
- Automatic password rotation
- Email and webhook notifications
- Comprehensive audit logging

Quick start:
    from tools.password import PasswordManager
    
    manager = PasswordManager()
    results = asyncio.run(
        manager.change_password(
            hosts=['server1', 'server2'],
            username='root',
            auto_generate=True
        )
    )
"""

from .models import (
    OperationStatus,
    ValidationSeverity,
    PasswordPolicy,
    ValidationResult,
    PasswordChangeResult,
    AuditEntry,
    RotationPolicy,
    RotationScheduleEntry,
    LDAPConfig,
    NotificationConfig,
    ChangeRequest
)

from .validators import (
    PasswordValidator,
    PasswordHistoryValidator
)

from .generators import (
    PasswordGenerator,
    PasswordPatternGenerator
)

from .executor import (
    RemotePasswordExecutor,
    SSHExecutor
)

from .auditor import AuditLogger

from .ldap_sync import (
    LDAPSync,
    LDAPCredentialStore
)

from .scheduler import PasswordRotationScheduler

from .notifier import (
    EmailNotifier,
    WebhookNotifier,
    NotificationManager
)

from .manager import PasswordManager

from .password_commands import password_group

__version__ = "1.0.0"

__all__ = [
    # Models
    "OperationStatus",
    "ValidationSeverity",
    "PasswordPolicy",
    "ValidationResult",
    "PasswordChangeResult",
    "AuditEntry",
    "RotationPolicy",
    "RotationScheduleEntry",
    "LDAPConfig",
    "NotificationConfig",
    "ChangeRequest",
    # Validators
    "PasswordValidator",
    "PasswordHistoryValidator",
    # Generators
    "PasswordGenerator",
    "PasswordPatternGenerator",
    # Executor
    "RemotePasswordExecutor",
    "SSHExecutor",
    # Auditor
    "AuditLogger",
    # LDAP
    "LDAPSync",
    "LDAPCredentialStore",
    # Scheduler
    "PasswordRotationScheduler",
    # Notifier
    "EmailNotifier",
    "WebhookNotifier",
    "NotificationManager",
    # Manager
    "PasswordManager",
    # CLI
    "password_group",
]
