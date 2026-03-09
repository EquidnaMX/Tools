"""Backup CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from tools.backup import BackupError, BackupManager


@click.group(name="backup")
def backup() -> None:
    """Backup utilities with local rotation support."""
    pass


@backup.command(name="create")
@click.argument("source", type=click.Path(exists=True))
@click.option("--backup-dir", required=True, type=click.Path(), help="Directory where backups are stored")
@click.option("--name", default=None, help="Optional base name for backup file")
@click.option("--keep", default=7, show_default=True, type=int, help="Retention limit after backup")
def create_backup(source: str, backup_dir: str, name: str | None, keep: int) -> None:
    """Create a backup and apply retention rotation."""
    try:
        manager = BackupManager(Path(backup_dir), keep=keep)
        backup_file = manager.create_backup(source=Path(source), name=name)
        removed = manager.apply_rotation(prefix=(name or Path(source).name), keep=keep)

        click.secho(f"Backup created: {backup_file}", fg="green")
        if removed:
            click.echo(f"Removed {len(removed)} old backup(s):")
            for item in removed:
                click.echo(f"  - {item}")
    except BackupError as exc:
        raise click.ClickException(str(exc))


@backup.command(name="list")
@click.option("--backup-dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--prefix", default=None, help="Filter by backup filename prefix")
def list_backups(backup_dir: str, prefix: str | None) -> None:
    """List available backups."""
    manager = BackupManager(Path(backup_dir))
    items = manager.list_backups(prefix=prefix)

    if not items:
        click.echo("No backups found.")
        return

    for item in items:
        click.echo(str(item.path))


@backup.command(name="rotate")
@click.option("--backup-dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--prefix", default=None, help="Filter by backup filename prefix")
@click.option("--keep", required=True, type=int, help="Number of newest backups to keep")
def rotate_backups(backup_dir: str, prefix: str | None, keep: int) -> None:
    """Apply retention policy to existing backups."""
    try:
        manager = BackupManager(Path(backup_dir), keep=keep)
        deleted = manager.apply_rotation(prefix=prefix, keep=keep)
        click.echo(f"Deleted {len(deleted)} backup(s).")
    except BackupError as exc:
        raise click.ClickException(str(exc))


@backup.command(name="restore")
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--destination", required=True, type=click.Path(), help="Directory where backup is restored")
@click.option("--overwrite", is_flag=True, help="Overwrite extracted root if it already exists")
def restore_backup(backup_file: str, destination: str, overwrite: bool) -> None:
    """Restore a backup archive into destination."""
    try:
        manager = BackupManager(Path(destination))
        extracted = manager.restore_backup(
            backup_file=Path(backup_file), destination=Path(destination), overwrite=overwrite
        )
        click.secho(f"Backup restored to: {extracted}", fg="green")
    except BackupError as exc:
        raise click.ClickException(str(exc))
