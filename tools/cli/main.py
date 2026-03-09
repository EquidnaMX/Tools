"""
Main CLI entry point for tools-admin toolkit.
"""

import click
from pathlib import Path

from tools.core.logger import setup_logging, get_logger
from tools.core.config import ConfigManager
from tools.cli.remote_commands import remote
from tools.cli.mail_commands import mail
from tools.cli.dns_commands import dns
from tools.cli.system_commands import system
from tools.cli.cloud_commands import cloud
from tools.cli.backup_commands import backup
from tools.cli.monitoring_commands import monitoring

logger = get_logger(__name__)


@click.group()
@click.version_option(version="2.8.0", prog_name="tools")
@click.option("--config", type=click.Path(), help="Path to config file")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
@click.pass_context
def cli(ctx, config, log_level):
    """
    Tools Admin Toolkit - Complete Python toolkit for Linux server administration.

    Unified interfaces for remote management, mail auditing, DNS management,
    system utilities, and cloud storage synchronization.
    """
    # Initialize logging
    setup_logging(
        level=getattr(__import__("logging"), log_level),
        format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load configuration
    ctx.ensure_object(dict)
    config_path = Path(config) if config else None
    try:
        ctx.obj["config"] = ConfigManager(config_path)
        logger.debug(f"Config loaded from: {config_path or 'auto-discovery'}")
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        ctx.obj["config"] = None


# Register command groups
cli.add_command(remote)
cli.add_command(mail)
cli.add_command(dns)
cli.add_command(system)
cli.add_command(cloud)
cli.add_command(backup)
cli.add_command(monitoring)


@cli.command()
@click.pass_context
def config(ctx):
    """Manage configuration profiles."""
    config_manager = ctx.obj.get("config")
    if config_manager:
        profiles = config_manager.list_profiles()
        if profiles:
            click.echo("Available profiles:")
            for profile in profiles:
                click.echo(f"  - {profile}")
        else:
            click.echo("No profiles found")
    else:
        click.echo("Configuration not loaded")


if __name__ == "__main__":
    cli()
