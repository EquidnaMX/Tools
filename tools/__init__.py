"""
Tools Admin Toolkit - Complete Python toolkit for Linux server administration and auditing.

Provides unified interfaces for remote management, mail auditing, DNS management,
system utilities, and multi-cloud storage synchronization.

Features:
- Remote server management (SSH execution, file distribution, network scanning)
- Mail auditing (SPF/DKIM/DMARC validation, domain health monitoring)
- DNS management and zone replication checking
- System utilities (timezone management, file operations, PAM configuration)
- Multi-cloud storage support (AWS S3, Google Cloud, Azure Blob, DigitalOcean Spaces)

Version: 2.6.0 - Multi-cloud storage support
"""

__version__ = "2.6.0"
__author__ = "gruelasjr"
__all__ = ["remote", "mail", "dns", "system", "cloud", "core", "cli"]
