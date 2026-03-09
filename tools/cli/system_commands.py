"""
System utilities CLI subcommands.
Provides: tools system timezone, tools system files
"""

from pathlib import Path
from typing import Optional

import click

from tools.core.logger import get_logger
from tools.system.timezone_manager import TimezoneManager, TimezoneError
from tools.system.file_manager import FileManager, FileManagerError
from tools.system.pam_manager import PAMManager, PAMManagerError

logger = get_logger(__name__)


@click.group(name="system")
def system() -> None:
    """System utilities: timezone, file operations, configuration."""
    pass


# ============================================================================
# TIMEZONE COMMANDS
# ============================================================================

@system.group(name="timezone")
def timezone() -> None:
    """Manage system timezone configuration."""
    pass


@timezone.command(name="get")
def timezone_get() -> None:
    """Get current system timezone."""
    try:
        manager = TimezoneManager()
        current_tz = manager.get_current_timezone()
        
        click.echo(f"Current timezone: {current_tz}")
        
        # Show detailed info
        info = manager.get_timezone_info()
        click.echo(f"Platform: {info['platform']}")
        
    except TimezoneError as e:
        logger.error(f"Failed to get timezone: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@timezone.command(name="set")
@click.argument("timezone", type=str)
@click.option(
    "--no-sudo",
    is_flag=True,
    help="Don't use sudo (may require running as root)"
)
def timezone_set(timezone: str, no_sudo: bool) -> None:
    """
    Set system timezone.
    
    TIMEZONE: Timezone string (e.g., 'America/Mexico_City', 'UTC')
    """
    try:
        manager = TimezoneManager()
        
        # Confirm action
        current = manager.get_current_timezone()
        click.echo(f"Current timezone: {current}")
        click.echo(f"New timezone: {timezone}")
        
        if not click.confirm("Do you want to proceed?"):
            click.echo("Aborted.")
            return
        
        # Set timezone
        manager.set_timezone(timezone, sudo=not no_sudo)
        
        # Verify
        new_tz = manager.get_current_timezone()
        click.secho(f"✓ Timezone set to: {new_tz}", fg="green")
        
    except TimezoneError as e:
        logger.error(f"Failed to set timezone: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@timezone.command(name="list")
@click.option(
    "--filter",
    "-f",
    type=str,
    help="Filter timezones by region (e.g., 'America', 'Europe')"
)
def timezone_list(filter: Optional[str]) -> None:
    """List available timezones."""
    try:
        manager = TimezoneManager()
        timezones = manager.list_available_timezones()
        
        if filter:
            timezones = [tz for tz in timezones if filter in tz]
        
        click.echo(f"Available timezones ({len(timezones)}):")
        for tz in timezones:
            click.echo(f"  {tz}")
            
    except TimezoneError as e:
        logger.error(f"Failed to list timezones: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@timezone.command(name="info")
def timezone_info() -> None:
    """Show detailed timezone information."""
    try:
        manager = TimezoneManager()
        info = manager.get_timezone_info()
        
        click.echo("=" * 60)
        click.echo("TIMEZONE INFORMATION")
        click.echo("=" * 60)
        
        for key, value in info.items():
            if key == "raw_output":
                click.echo(f"\n{value}")
            else:
                click.echo(f"{key}: {value}")
                
    except TimezoneError as e:
        logger.error(f"Failed to get timezone info: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


# ============================================================================
# FILE COMMANDS
# ============================================================================

@system.group(name="files")
def files() -> None:
    """File management operations."""
    pass


@files.command(name="clean-empty")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--recursive/--no-recursive",
    "-r/-R",
    default=True,
    help="Search subdirectories (default: recursive)"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without actually deleting"
)
def files_clean_empty(directory: str, recursive: bool, dry_run: bool) -> None:
    """
    Delete empty files or files with only whitespace.
    
    DIRECTORY: Directory to scan for empty files
    """
    try:
        manager = FileManager()
        dir_path = Path(directory)
        
        click.echo(f"Scanning: {dir_path}")
        click.echo(f"Recursive: {recursive}")
        
        if dry_run:
            click.secho("DRY RUN MODE - No files will be deleted", fg="yellow")
        
        stats = manager.delete_empty_files(
            directory=dir_path,
            recursive=recursive,
            dry_run=dry_run
        )
        
        click.echo("\n" + "=" * 60)
        click.echo("RESULTS")
        click.echo("=" * 60)
        click.echo(f"Files processed: {stats.processed}")
        click.echo(f"Files deleted: {stats.deleted}")
        click.echo(f"Total size freed: {stats.total_size:,} bytes")
        click.echo(f"Errors: {stats.errors}")
        
        if stats.deleted > 0:
            click.secho(f"\n✓ Successfully cleaned {stats.deleted} empty files", fg="green")
        else:
            click.echo("\nNo empty files found.")
            
    except FileManagerError as e:
        logger.error(f"Failed to clean empty files: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@files.command(name="merge")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("output_file", type=click.Path())
@click.option(
    "--pattern",
    "-p",
    default="*",
    help="File pattern to match (e.g., '*.txt', '*.log')"
)
@click.option(
    "--recursive/--no-recursive",
    "-r/-R",
    default=False,
    help="Include subdirectories (default: no)"
)
@click.option(
    "--exclude-empty-lines",
    is_flag=True,
    help="Skip empty lines when merging"
)
@click.option(
    "--separator",
    "-s",
    type=str,
    help="Separator text between files (e.g., '---')"
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite output file if it exists"
)
def files_merge(
    source_dir: str,
    output_file: str,
    pattern: str,
    recursive: bool,
    exclude_empty_lines: bool,
    separator: Optional[str],
    overwrite: bool
) -> None:
    """
    Merge multiple files into a single output file.
    
    SOURCE_DIR: Directory containing files to merge
    OUTPUT_FILE: Path to output file
    """
    try:
        manager = FileManager()
        src_path = Path(source_dir)
        out_path = Path(output_file)
        
        click.echo(f"Source directory: {src_path}")
        click.echo(f"Output file: {out_path}")
        click.echo(f"Pattern: {pattern}")
        click.echo(f"Recursive: {recursive}")
        
        if exclude_empty_lines:
            click.echo("Empty lines will be excluded")
        
        if separator:
            click.echo(f"Separator: '{separator}'")
        
        stats = manager.merge_files(
            source_dir=src_path,
            output_file=out_path,
            exclude_empty_lines=exclude_empty_lines,
            pattern=pattern,
            recursive=recursive,
            separator=separator,
            overwrite=overwrite
        )
        
        click.echo("\n" + "=" * 60)
        click.echo("RESULTS")
        click.echo("=" * 60)
        click.echo(f"Files processed: {stats.processed}")
        click.echo(f"Files merged: {stats.merged}")
        click.echo(f"Total size: {stats.total_size:,} bytes")
        click.echo(f"Errors: {stats.errors}")
        
        if stats.merged > 0:
            click.secho(f"\n✓ Successfully merged {stats.merged} files into {out_path}", fg="green")
        else:
            click.secho("\n⚠ No files were merged", fg="yellow")
            
    except FileManagerError as e:
        logger.error(f"Failed to merge files: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@files.command(name="stats")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format"
)
def files_stats(directory: str, output_json: bool) -> None:
    """
    Get statistics about a directory.
    
    DIRECTORY: Directory to analyze
    """
    try:
        manager = FileManager()
        dir_path = Path(directory)
        
        stats = manager.get_directory_stats(dir_path)
        
        if output_json:
            import json
            click.echo(json.dumps(stats, indent=2))
        else:
            click.echo("=" * 60)
            click.echo(f"DIRECTORY STATISTICS: {stats['path']}")
            click.echo("=" * 60)
            click.echo(f"Total files: {stats['total_files']:,}")
            click.echo(f"Total directories: {stats['total_dirs']:,}")
            click.echo(f"Total size: {stats['total_size']:,} bytes ({stats['total_size'] / (1024*1024):.2f} MB)")
            click.echo(f"Empty files: {stats['empty_files']:,}")
            
            if stats['largest_file']:
                click.echo(f"\nLargest file: {stats['largest_file']}")
                click.echo(f"Size: {stats['largest_size']:,} bytes ({stats['largest_size'] / (1024*1024):.2f} MB)")
                
    except FileManagerError as e:
        logger.error(f"Failed to get directory stats: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@files.command(name="find")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.argument("pattern", type=str)
@click.option(
    "--regex",
    is_flag=True,
    help="Treat pattern as regular expression"
)
@click.option(
    "--recursive/--no-recursive",
    "-r/-R",
    default=True,
    help="Search subdirectories (default: recursive)"
)
def files_find(directory: str, pattern: str, regex: bool, recursive: bool) -> None:
    """
    Find files matching a pattern.
    
    DIRECTORY: Directory to search
    PATTERN: Glob pattern or regex pattern
    """
    try:
        manager = FileManager()
        dir_path = Path(directory)
        
        matches = manager.find_files_by_pattern(
            directory=dir_path,
            pattern=pattern,
            regex=regex,
            recursive=recursive
        )
        
        if matches:
            click.echo(f"Found {len(matches)} matching files:\n")
            for file_path in matches:
                size = file_path.stat().st_size
                click.echo(f"  {file_path} ({size:,} bytes)")
        else:
            click.echo(f"No files found matching: {pattern}")
            
    except FileManagerError as e:
        logger.error(f"Failed to find files: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


# ============================================================================
# PAM COMMANDS
# ============================================================================

@system.group(name="pam")
def pam() -> None:
    """PAM configuration inspection and maintenance."""
    pass


@pam.command(name="list")
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
def pam_list(pam_dir: str) -> None:
    """List PAM service files."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        services = manager.list_services()

        click.echo(f"PAM services in {pam_dir} ({len(services)}):")
        for info in services:
            click.echo(f"  {info.service} ({info.size_bytes:,} bytes)")

    except PAMManagerError as e:
        logger.error(f"Failed to list PAM services: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="show")
@click.argument("service", type=str)
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
def pam_show(service: str, pam_dir: str) -> None:
    """Show PAM configuration for SERVICE."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        content = manager.read_service(service)
        click.echo(content)

    except PAMManagerError as e:
        logger.error(f"Failed to show PAM service {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="check")
@click.argument("service", type=str)
@click.option("--module", "module_name", required=True, help="PAM module name (e.g., pam_faillock.so)")
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
def pam_check(service: str, module_name: str, pam_dir: str) -> None:
    """Check whether a PAM MODULE is enabled for SERVICE."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        enabled = manager.check_module_enabled(service, module_name)

        if enabled:
            click.secho(f"✓ Module {module_name} is enabled in {service}", fg="green")
        else:
            click.secho(f"✗ Module {module_name} is not enabled in {service}", fg="yellow")
            raise click.exceptions.Exit(1)

    except PAMManagerError as e:
        logger.error(f"Failed to check PAM module in {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="backup")
@click.argument("service", type=str)
@click.option("--backup-dir", type=click.Path(file_okay=False), default="./pam_backups", show_default=True)
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
def pam_backup(service: str, backup_dir: str, pam_dir: str) -> None:
    """Create timestamped backup for a PAM SERVICE file."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        backup_path = manager.create_backup(service, Path(backup_dir))
        click.secho(f"✓ Backup created: {backup_path}", fg="green")

    except PAMManagerError as e:
        logger.error(f"Failed to create PAM backup for {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="restore")
@click.argument("service", type=str)
@click.option("--backup", "backup_file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
@click.option("--dry-run", is_flag=True, help="Show restore action without writing")
def pam_restore(service: str, backup_file: str, pam_dir: str, dry_run: bool) -> None:
    """Restore a backup file into PAM SERVICE."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        manager.restore_backup(service, Path(backup_file), dry_run=dry_run)

        if dry_run:
            click.secho("✓ Dry-run restore completed", fg="yellow")
        else:
            click.secho("✓ Restore completed", fg="green")

    except PAMManagerError as e:
        logger.error(f"Failed to restore PAM backup for {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="ensure-line")
@click.argument("service", type=str)
@click.option("--line", "line_text", required=True, help="Line that should exist in service file")
@click.option("--match-pattern", type=str, help="Regex to replace existing line")
@click.option("--after-pattern", type=str, help="Regex after which the line should be inserted")
@click.option("--backup-dir", type=click.Path(file_okay=False), help="Optional backup directory before write")
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
@click.option("--dry-run", is_flag=True, help="Show changes without writing")
@click.option("--diff", "show_diff", is_flag=True, help="Show unified diff of changes")
def pam_ensure_line(
    service: str,
    line_text: str,
    match_pattern: Optional[str],
    after_pattern: Optional[str],
    backup_dir: Optional[str],
    pam_dir: str,
    dry_run: bool,
    show_diff: bool,
) -> None:
    """Ensure a line exists (or is replaced) in PAM SERVICE file."""
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        result = manager.ensure_line(
            service=service,
            line=line_text,
            match_pattern=match_pattern,
            after_pattern=after_pattern,
            backup_dir=Path(backup_dir) if backup_dir else None,
            dry_run=dry_run,
            show_diff=show_diff,
        )

        if result.updated:
            click.secho(f"✓ PAM file updated: {service}", fg="green" if not dry_run else "yellow")
            if result.backup_path:
                click.echo(f"Backup: {result.backup_path}")
            if result.diff:
                click.echo("\nDiff preview:")
                click.echo(result.diff)
        else:
            click.echo(f"No changes needed for {service}")

    except PAMManagerError as e:
        logger.error(f"Failed to ensure line in {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@pam.command(name="harden")
@click.argument("service", type=str)
@click.option("--profile", type=str, help="Hardening profile name (default: same as service)")
@click.option("--list-profiles", is_flag=True, help="List available hardening profiles and exit")
@click.option("--backup-dir", type=click.Path(file_okay=False), default="./pam_backups", show_default=True)
@click.option("--pam-dir", type=click.Path(file_okay=False), default="/etc/pam.d", show_default=True)
@click.option("--dry-run", is_flag=True, help="Show changes without writing")
@click.option("--diff", "show_diff", is_flag=True, help="Show unified diff of changes")
def pam_harden(
    service: str,
    profile: Optional[str],
    list_profiles: bool,
    backup_dir: str,
    pam_dir: str,
    dry_run: bool,
    show_diff: bool,
) -> None:
    """Apply security hardening profile to PAM SERVICE."""
    from tools.system.pam_manager import HARDENING_PROFILES
    
    if list_profiles:
        click.echo("Available hardening profiles:")
        for profile_name in sorted(HARDENING_PROFILES.keys()):
            profile_lines = HARDENING_PROFILES[profile_name]
            click.echo(f"\n{profile_name}:")
            click.echo(f"  Lines: {len(profile_lines)}")
            click.echo(f"  Description: {profile_lines[0] if profile_lines else 'No description'}")
        return
    
    try:
        manager = PAMManager(pam_dir=Path(pam_dir))
        result = manager.apply_hardening(
            service=service,
            profile=profile,
            backup_dir=Path(backup_dir),
            dry_run=dry_run,
            show_diff=show_diff,
        )

        if result.applied:
            status = "Would apply" if dry_run else "Applied"
            click.secho(
                f"✓ {status} {result.profile} hardening profile to {service}",
                fg="yellow" if dry_run else "green"
            )
            if result.backup_path:
                click.echo(f"Backup: {result.backup_path}")
            if result.diff:
                click.echo("\nDiff preview:")
                click.echo(result.diff)
        else:
            click.echo(f"Hardening profile {result.profile} already applied to {service}")

    except PAMManagerError as e:
        logger.error(f"Failed to apply hardening to {service}: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
