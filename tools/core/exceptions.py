"""
Custom exceptions for tools modules.
"""


class ToolsException(Exception):
    """Base exception for all tools errors."""

    pass


class ValidationError(ToolsException):
    """Raised when input validation fails."""

    pass


class ConfigError(ToolsException):
    """Raised when configuration is invalid."""

    pass


class RemoteExecutionError(ToolsException):
    """Raised when remote command execution fails."""

    pass


class NetworkError(ToolsException):
    """Raised when network operations fail."""

    pass


class DistributionError(ToolsException):
    """Raised when file distribution fails."""

    pass


class DNSError(ToolsException):
    """Raised when DNS operations fail."""

    pass


class MailAuditError(ToolsException):
    """Raised when mail audit fails."""

    pass
