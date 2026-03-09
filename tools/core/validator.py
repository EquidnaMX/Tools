"""
Input validation and sanitization utilities.
"""

import re
from typing import Any, List, Pattern


class InputValidator:
    """Utility class for input validation and sanitization."""

    # Patterns for common validations
    IP_PATTERN: Pattern = re.compile(
        r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    )
    DOMAIN_PATTERN: Pattern = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z]{2,}$"
    )
    EMAIL_PATTERN: Pattern = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )
    PATH_PATTERN: Pattern = re.compile(r"^[/a-zA-Z0-9._\-~]*$")

    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Validate IPv4 address format."""
        return bool(InputValidator.IP_PATTERN.match(ip))

    @staticmethod
    def validate_domain(domain: str) -> bool:
        """Validate domain name format."""
        return bool(InputValidator.DOMAIN_PATTERN.match(domain))

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address format."""
        return bool(InputValidator.EMAIL_PATTERN.match(email))

    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate file path format."""
        return bool(InputValidator.PATH_PATTERN.match(path))

    @staticmethod
    def sanitize_command(command: str) -> str:
        """Sanitize shell command to prevent injection.

        Args:
            command: Command string to sanitize

        Returns:
            Sanitized command
        """
        # Remove potentially dangerous characters
        dangerous_chars = ["$", "`", ";", "|", "&", ">", "<", "(", ")"]
        sanitized = command
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def validate_not_empty(value: Any, name: str = "value") -> Any:
        """Validate that value is not empty."""
        if not value:
            raise ValueError(f"{name} cannot be empty")
        return value

    @staticmethod
    def validate_type(value: Any, expected_type: type, name: str = "value"):
        """Validate that value is of expected type."""
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{name} must be {expected_type.__name__},"
                f" got {type(value).__name__}"
            )
        return value

    @staticmethod
    def validate_in_list(
        value: Any, allowed_values: List[Any], name: str = "value"
    ) -> Any:
        """Validate that value is in list of allowed values."""
        if value not in allowed_values:
            raise ValueError(
                f"{name} must be one of {allowed_values}, got {value}"
            )
        return value
