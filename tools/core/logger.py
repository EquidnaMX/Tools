"""
Unified logging system for all tools modules.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    """Formatter with colored output for terminal."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.RESET)
        record.levelname = f"{color}{levelname}{self.RESET}"
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with unified configuration."""
    return logging.getLogger(name)


def setup_logging(
    level: int = logging.INFO,
    log_file: str = None,
    format_string: str = None,
) -> None:
    """
    Configure logging for all modules.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional file to write logs to
        format_string: Custom format string
    """
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler with colors
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(format_string)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # File handler if specified
        if log_file:
            log_path = Path(log_file).parent
            log_path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
            )
            file_handler.setLevel(level)
            file_formatter = logging.Formatter(format_string)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
