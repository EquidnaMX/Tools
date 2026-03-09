"""
Data models for password management module

Defines core data structures for password operations, validation results,
and audit logs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum


class OperationStatus(str, Enum):
    """Status of password operations"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    PARTIAL = "partial"
    PENDING = "pending"
    ROLLED_BACK = "rolled_back"


class ValidationSeverity(str, Enum):
    """Severity levels for validation errors"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class PasswordPolicy:
    """Password complexity and security policy"""
    
    # Length requirements
    min_length: int = 12
    max_length: int = 128
    
    # Character requirements
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*-_+=[]{}|;:,.<>?"
    
    # History and reuse
    max_reuse_history: int = 5
    min_age_days: int = 1
    max_age_days: int = 90
    
    # Excluded terms
    excluded_terms: List[str] = field(
        default_factory=lambda: ["password", "123456", "admin", "root", "test"]
    )
    
    # Ambiguous characters to exclude
    exclude_ambiguous: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary"""
        return {
            "min_length": self.min_length,
            "max_length": self.max_length,
            "require_uppercase": self.require_uppercase,
            "require_lowercase": self.require_lowercase,
            "require_digits": self.require_digits,
            "require_special": self.require_special,
            "max_reuse_history": self.max_reuse_history,
            "min_age_days": self.min_age_days,
            "max_age_days": self.max_age_days,
        }


@dataclass
class ValidationResult:
    """Result of password validation"""
    
    valid: bool
    score: int = 0  # 0-100, fortaleza de contraseña
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    entropy_bits: float = 0.0
    
    def is_valid(self) -> bool:
        """Check if password is valid"""
        return self.valid and len(self.errors) == 0


@dataclass
class PasswordChangeResult:
    """Result of a password change operation"""
    
    host: str
    username: str
    status: OperationStatus
    duration: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    verified: bool = False
    error: Optional[str] = None
    retry_available: bool = True
    method: Optional[str] = None  # 'passwd', 'chpasswd', etc
    output: Optional[str] = None
    
    def __post_init__(self):
        """Ensure timestamp is datetime"""
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
    
    def is_success(self) -> bool:
        """Check if operation was successful"""
        return self.status == OperationStatus.SUCCESS and self.verified


@dataclass
class AuditEntry:
    """Audit log entry for password changes"""
    
    id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    operation: str = ""  # 'change_initiated', 'change_success', 'change_failed'
    
    # Who and where
    operator: str = ""  # usuario@domain que ejecuta
    host: str = ""
    username: str = ""
    
    # Result
    status: OperationStatus = OperationStatus.PENDING
    result_code: int = 0
    result_message: str = ""
    
    # Details
    duration: float = 0.0
    verified: bool = False
    method: Optional[str] = None
    
    # Metadata
    ldap_synced: bool = False
    rollback_executed: bool = False
    notifications_sent: List[str] = field(default_factory=list)  # email, webhook
    
    # Security
    password_hash: Optional[str] = None  # SHA256 del hash anterior (NO la contraseña)
    ip_address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (safe, without actual passwords)"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "operator": self.operator,
            "host": self.host,
            "username": self.username,
            "status": self.status.value,
            "duration": self.duration,
            "verified": self.verified,
            "method": self.method,
            "ldap_synced": self.ldap_synced,
            "rollback_executed": self.rollback_executed,
            "notifications_sent": self.notifications_sent,
        }


@dataclass
class RotationPolicy:
    """Policy for automatic password rotation"""
    
    enabled: bool = False
    
    # Rotation schedule
    rotation_interval_days: int = 30
    rotate_on_days: List[int] = field(default_factory=lambda: [0])  # 0=Sunday, 6=Saturday
    rotate_at_hour: int = 2  # 2 AM
    rotate_at_minute: int = 0
    
    # Rotation scope
    hosts: List[str] = field(default_factory=list)
    users: List[str] = field(default_factory=list)
    
    # Rotation behavior
    auto_generate: bool = True
    notify_users: bool = True
    ldap_sync: bool = True
    verify_change: bool = True
    
    def next_rotation(self) -> datetime:
        """Calculate next rotation time"""
        now = datetime.now()
        next_run = now.replace(hour=self.rotate_at_hour, minute=self.rotate_at_minute, second=0)
        
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run


@dataclass
class LDAPConfig:
    """LDAP configuration for synchronization"""
    
    server_uri: str  # ldap://host:389 o ldaps://host:636
    bind_dn: str  # CN=admin,DC=example,DC=com
    bind_password: str  # Encrypted
    
    base_dn: str  # DC=example,DC=com
    user_dn_template: Optional[str] = None  # Template para encontrar usuario
    
    # SSL/TLS
    use_ssl: bool = False  # ldaps://
    use_tls: bool = True   # STARTTLS
    verify_cert: bool = True
    ca_cert_path: Optional[str] = None
    
    # Connection
    timeout_seconds: int = 10
    pool_size: int = 10
    
    # Attributes to sync
    attributes_to_sync: List[str] = field(default_factory=lambda: [
        "mail",
        "telephoneNumber",
        "department",
        "description"
    ])

    def __post_init__(self):
        """Populate defaults that depend on other fields."""
        if not self.user_dn_template:
            self.user_dn_template = f"uid={{username}},{self.base_dn}"
    
    def to_connection_string(self) -> str:
        """Generate LDAP connection string (safe, without password)"""
        proto = "ldaps" if self.use_ssl else "ldap"
        return f"{proto}://{self.server_uri.split('://')[1]}"


@dataclass
class NotificationConfig:
    """Configuration for email and webhook notifications"""
    
    # Email
    email_enabled: bool = False
    smtp_server: str = "localhost"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_address: str = "password-manager@example.com"
    recipient_emails: List[str] = field(default_factory=list)
    
    # Webhooks
    webhook_enabled: bool = False
    webhook_urls: List[str] = field(default_factory=list)
    webhook_retry_count: int = 3
    webhook_timeout_seconds: int = 10
    
    # Notification events
    notify_on_success: bool = True
    notify_on_failure: bool = True
    notify_on_rotation: bool = True
    
    # Notification details
    include_results_in_email: bool = True
    include_audit_log: bool = False


@dataclass
class ChangeRequest:
    """Request to change password on multiple hosts"""
    
    id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # What to change
    username: str = ""
    hosts: List[str] = field(default_factory=list)
    
    # How to change
    old_password: Optional[str] = None
    new_password: Optional[str] = None
    auto_generate: bool = False
    
    # Execution options
    parallel_jobs: int = 3
    timeout_seconds: int = 30
    verify: bool = True
    rollback_on_failure: bool = True
    
    # Operator info
    operator: str = ""
    reason: str = ""
    
    # Confirmation
    confirmed: bool = False
    confirmed_at: Optional[datetime] = None
    
    # Execution state
    status: OperationStatus = OperationStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class RotationScheduleEntry:
    """Single entry in rotation schedule"""
    
    id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    username: str = ""
    host: str = ""
    
    last_rotation: Optional[datetime] = None
    next_rotation: Optional[datetime] = None
    
    rotation_enabled: bool = True
    days_until_next: int = 0
    
    def is_due(self) -> bool:
        """Check if rotation is due"""
        if not self.rotation_enabled or not self.next_rotation:
            return False
        return datetime.utcnow() >= self.next_rotation
