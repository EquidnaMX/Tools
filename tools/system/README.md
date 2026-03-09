# System Utilities Module

## Overview

The `system` module provides cross-platform utilities for system administration tasks including timezone management, file operations, and PAM configuration management.

## Features

### Timezone Management (`TimezoneManager`)

Manage system timezone configuration across Linux, Windows, and macOS.

**Capabilities:**

- Get current timezone
- Set system timezone
- List available timezones
- Get detailed timezone information

**CLI Commands:**

```bash
# Get current timezone
tools system timezone get

# Set timezone
tools system timezone set America/Mexico_City

# List available timezones
tools system timezone list

# Filter timezones by region
tools system timezone list --filter America

# Show detailed info
tools system timezone info
```

**Python API:**

```python
from tools.system import TimezoneManager

manager = TimezoneManager()

# Get current timezone
tz = manager.get_current_timezone()
print(f"Current: {tz}")

# Set timezone (requires sudo on Linux/macOS)
manager.set_timezone("UTC", sudo=True)

# List available timezones
zones = manager.list_available_timezones()
```

### File Management (`FileManager`)

Batch file operations and cleanup utilities.

**Capabilities:**

- Delete empty or whitespace-only files
- Merge multiple files into one
- Find files by pattern (glob or regex)
- Get directory statistics

**CLI Commands:**

```bash
# Delete empty files
tools system files clean-empty /path/to/dir --recursive

# Dry run (preview what would be deleted)
tools system files clean-empty /path/to/dir --dry-run

# Merge files
tools system files merge /source/dir output.txt --pattern "*.log"

# Merge with separator between files
tools system files merge /source/dir output.txt --separator "---"

# Exclude empty lines when merging
tools system files merge /source/dir output.txt --exclude-empty-lines

# Find files matching pattern
tools system files find /path/to/dir "*.txt" --recursive

# Find with regex
tools system files find /path/to/dir "test_\d+\.log" --regex

# Get directory statistics
tools system files stats /path/to/dir

# Output stats as JSON
tools system files stats /path/to/dir --json
```

**Python API:**

```python
from tools.system import FileManager
from pathlib import Path

manager = FileManager()

# Delete empty files
stats = manager.delete_empty_files(
    directory=Path("/path/to/dir"),
    recursive=True,
    dry_run=False
)
print(f"Deleted {stats.deleted} files")

# Merge files
stats = manager.merge_files(
    source_dir=Path("/source"),
    output_file=Path("merged.txt"),
    pattern="*.txt",
    exclude_empty_lines=True,
    separator="---"
)

# Find files
matches = manager.find_files_by_pattern(
    directory=Path("/path"),
    pattern="*.log",
    recursive=True
)

# Get directory stats
stats = manager.get_directory_stats(Path("/path"))
print(f"Total files: {stats['total_files']}")
print(f"Total size: {stats['total_size']} bytes")
```

### PAM Management (`PAMManager`) ⭐ NEW

Safely inspect and maintain PAM files (typically under `/etc/pam.d`).

**Capabilities:**

- List PAM service files
- Read a service file
- Check if a PAM module is enabled
- Create timestamped backups
- Restore from backup
- Ensure or replace a line using regex patterns
- **Apply security hardening profiles** 🔐 NEW
- **Preview changes with unified diff** 📊 NEW

**CLI Commands:**

```bash
# List PAM service files
tools system pam list

# Show service file
tools system pam show sshd

# Check whether a module is enabled
tools system pam check sshd --module pam_faillock.so

# Create backup
tools system pam backup sshd --backup-dir ./pam_backups

# Restore from backup
tools system pam restore sshd --backup ./pam_backups/sshd.20260307_120000.bak

# Ensure a line exists (replace or insert) with diff preview
tools system pam ensure-line sshd \
  --line "auth required pam_faillock.so preauth silent" \
  --match-pattern "pam_faillock\\.so" \
  --backup-dir ./pam_backups \
  --diff

# Apply security hardening profile
tools system pam harden sshd --backup-dir ./pam_backups --diff

# List available hardening profiles
tools system pam harden sshd --list-profiles

# Apply hardening with dry-run mode
tools system pam harden login --dry-run --diff

# Apply custom profile to a service
tools system pam harden custom-service --profile sshd --diff
```

**Available Hardening Profiles:**

- `sshd` - Security hardening for SSH authentication
  - Account lockout after failed attempts (pam_faillock.so)
  - Password complexity requirements (pam_pwquality.so)
  - SHA-512 password hashing
- `login` - Security hardening for console login
  - Secure TTY enforcement (pam_securetty.so)
  - Enhanced account lockout policies
  - Access control and time restrictions
  - Login attempt logging
- `su` - Security hardening for su command
  - Wheel group requirement (pam_wheel.so)
  - Root privilege escalation protection
  - Enhanced authentication tracking

**Python API:**

```python
from pathlib import Path
from tools.system import PAMManager

pam = PAMManager(pam_dir=Path("/etc/pam.d"))

# List files
services = pam.list_services()

# Check module
enabled = pam.check_module_enabled("sshd", "pam_faillock.so")

# Backup + controlled update with diff
pam.create_backup("sshd", Path("./pam_backups"))
result = pam.ensure_line(
    service="sshd",
    line="auth required pam_faillock.so preauth silent",
    match_pattern=r"pam_faillock\\.so",
    show_diff=True,
)
if result.diff:
    print("Changes preview:")
    print(result.diff)

# Apply hardening profile
result = pam.apply_hardening(
    service="sshd",
    backup_dir=Path("./pam_backups"),
    show_diff=True,
    dry_run=False,
)
print(f"Applied {result.profile} profile: {result.applied}")
if result.diff:
    print(result.diff)
```

## Migration from Bash Scripts

This module replaces the following bash scripts from `system_utils/`:

| Bash Script             | Python Equivalent                  | CLI Command                      |
| ----------------------- | ---------------------------------- | -------------------------------- |
| `configure_timezone.sh` | `TimezoneManager`                  | `tools system timezone set`      |
| `delete_empty_files.sh` | `FileManager.delete_empty_files()` | `tools system files clean-empty` |
| `merge_files.sh`        | `FileManager.merge_files()`        | `tools system files merge`       |

**Advantages of Python version:**

- Cross-platform (Linux, Windows, macOS)
- Better error handling
- Dry-run mode for safety
- Comprehensive testing (54 unit tests)
- Structured logging
- Progress reporting
- Type hints and documentation

## Testing

The module includes comprehensive unit tests:

```bash
# Run system module tests
pytest tests/system/ -v

# Run with coverage
pytest tests/system/ --cov=tools.system --cov-report=html
```

**Test Coverage:**

- TimezoneManager: 12 tests (Linux, Windows, macOS scenarios)
- FileManager: 20 tests (file operations, edge cases)
- PAMManager: 22 tests (inspection, backup/restore, line updates, hardening, diff)

## Error Handling

All operations raise specific exceptions:

- `TimezoneError` - Timezone operations fail
- `FileManagerError` - File operations fail
- `PAMManagerError` - PAM operations fail

Both inherit from `ToolsException` for consistent error handling.

## Platform Support

| Feature         | Linux              | Windows             | macOS              |
| --------------- | ------------------ | ------------------- | ------------------ |
| Get timezone    | ✅                 | ✅                  | ✅                 |
| Set timezone    | ✅ (requires sudo) | ✅ (requires admin) | ✅ (requires sudo) |
| List timezones  | ✅                 | ✅                  | ✅                 |
| File operations | ✅                 | ✅                  | ✅                 |

## Examples

### Example 1: Clean Empty Log Files

```bash
# Preview what would be deleted
tools system files clean-empty /var/log/app --dry-run --recursive

# Actually delete them
tools system files clean-empty /var/log/app --recursive
```

### Example 2: Merge All Configuration Files

```bash
# Merge all .conf files with separators
tools system files merge /etc/myapp configs-backup.txt \
  --pattern "*.conf" \
  --recursive \
  --separator "# ===================="
```

### Example 3: Configure Server Timezone

```bash
# Set timezone on new server
tools system timezone set America/Mexico_City

# Verify
tools system timezone get
```

### Example 4: Find Large Files

```python
from tools.system import FileManager
from pathlib import Path

manager = FileManager()

# Get stats
stats = manager.get_directory_stats(Path("/var/log"))

if stats['largest_size'] > 100 * 1024 * 1024:  # 100MB
    print(f"Large file found: {stats['largest_file']}")
    print(f"Size: {stats['largest_size'] / (1024*1024):.2f} MB")
```

## Future Enhancements

Potential additions to the system module:

- User/group management
- Service management (systemd, etc.)
- Package management wrapper
- System monitoring utilities
- Disk space management
- Log rotation utilities
