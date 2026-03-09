"""
Remote management CLI subcommands for SSH execution and file distribution.
Provides: tools remote exec, tools remote upload, tools remote scan
"""

from pathlib import Path
from typing import Optional

import click

from tools.core.logger import get_logger
from tools.core.reporter import JSONReporter, CSVReporter
from tools.remote.ssh_executor import SSHExecutor
from tools.remote.file_distributor import FileDistributor
from tools.remote.network_scanner import NetworkScanner

logger = get_logger(__name__)


@click.group(name="remote")
def remote() -> None:
    """Remote management: execute commands, distribute files, scan networks."""
    pass


@remote.command(name="exec")
@click.argument("command", type=str)
@click.option(
    "--hosts",
    "-h",
    multiple=True,
    required=True,
    help="Target hosts (can repeat)",
)
@click.option(
    "--user",
    "-u",
    default="root",
    help="Remote user (default: root)",
)
@click.option(
    "--key",
    "-k",
    type=click.Path(exists=True),
    help="Path to SSH private key",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=30,
    help="SSH timeout in seconds (default: 30)",
)
@click.option(
    "--retries",
    "-r",
    type=int,
    default=2,
    help="Number of retries (default: 2)",
)
@click.option(
    "--parallel",
    "-p",
    type=int,
    default=5,
    help="Parallel worker count (default: 5)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json", "csv"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--output-file",
    type=click.Path(),
    help="Save output to file",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be executed without running",
)
@click.pass_context
def exec_command(
    ctx,
    command: str,
    hosts: tuple,
    user: str,
    key: Optional[str],
    timeout: int,
    retries: int,
    parallel: int,
    output: str,
    output_file: Optional[str],
    dry_run: bool,
) -> None:
    """Execute command on multiple remote hosts."""
    try:
        if dry_run:
            click.echo(f"DRY RUN: Would execute on {len(hosts)} hosts")
            for host in hosts:
                click.echo(f"  {host}: {command}")
            return

        key_path = Path(key) if key else None
        executor = SSHExecutor(
            user=user,
            key_path=key_path,
            timeout=timeout,
            max_retries=retries,
        )

        results, stats = executor.execute(
            hosts=list(hosts),
            command=command,
            parallel=parallel,
        )

        if output == "json":
            data = {
                "stats": stats.to_dict(),
                "results": [r.to_dict() for r in results],
            }
            reporter = JSONReporter()
            if output_file:
                reporter.write(data, Path(output_file))
                click.echo(f"Output saved to {output_file}")
            else:
                click.echo(JSONReporter().format(data))

        elif output == "csv":
            reporter = CSVReporter()
            if output_file:
                reporter.write([r.to_dict() for r in results], Path(output_file))
                click.echo(f"Output saved to {output_file}")
            else:
                click.echo("CSV output:")
                for r in results:
                    click.echo(str(r.to_dict()))

        else:  # text output
            click.echo(f"\n{'Results':=^60}")
            for result in results:
                status = "✓" if result.success else "✗"
                click.echo(f"{status} {result.host}")
                if result.stdout:
                    click.echo(f"  STDOUT: {result.stdout[:100]}")
                if result.stderr:
                    click.echo(f"  STDERR: {result.stderr[:100]}")

            click.echo(f"\n{'Summary':=^60}")
            click.echo(f"Total: {stats.total_hosts} hosts")
            click.echo(f"Success: {stats.successful}")
            click.echo(f"Failed: {stats.failed}")
            click.echo(f"Duration: {stats.total_duration:.2f}s")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise click.ClickException(str(e))


@remote.command(name="upload")
@click.argument("local_path", type=click.Path(exists=True))
@click.argument("remote_path", type=str)
@click.option(
    "--hosts",
    "-h",
    multiple=True,
    required=True,
    help="Target hosts (can repeat)",
)
@click.option(
    "--user",
    "-u",
    default="root",
    help="Remote user (default: root)",
)
@click.option(
    "--key",
    "-k",
    type=click.Path(exists=True),
    help="Path to SSH private key",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=30,
    help="SCP timeout in seconds (default: 30)",
)
@click.option(
    "--parallel",
    "-p",
    type=int,
    default=5,
    help="Parallel transfer count (default: 5)",
)
@click.option(
    "--compress",
    "-c",
    is_flag=True,
    help="Compress directory as tar.gz before transfer",
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    help="Exclude patterns (can repeat, e.g. *.pyc, __pycache__)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be uploaded without transferring",
)
def upload_command(
    local_path: str,
    remote_path: str,
    hosts: tuple,
    user: str,
    key: Optional[str],
    timeout: int,
    parallel: int,
    compress: bool,
    exclude: tuple,
    output: str,
    dry_run: bool,
) -> None:
    """Upload file or directory to multiple remote hosts."""
    try:
        local = Path(local_path)
        key_path = Path(key) if key else None

        distributor = FileDistributor(
            user=user,
            key_path=key_path,
            timeout=timeout,
            exclude_patterns=list(exclude),
            dry_run=dry_run,
        )

        if local.is_dir():
            results, distribution_result = distributor.upload_directory(
                hosts=list(hosts),
                local_dir=local,
                remote_path=remote_path,
                compress=compress,
                parallel=parallel,
            )
        else:
            results, distribution_result = distributor.upload_file(
                hosts=list(hosts),
                local_path=local,
                remote_path=remote_path,
                parallel=parallel,
            )

        if output == "json":
            data = {
                "stats": distribution_result.to_dict(),
                "results": [r.to_dict() for r in results],
            }
            click.echo(JSONReporter().format(data))
        else:  # text output
            click.echo(f"\n{'Upload Results':=^60}")
            for result in results:
                status = "✓" if result.success else "✗"
                size_mb = result.size_bytes / 1024 / 1024
                click.echo(f"{status} {result.host}: {size_mb:.2f} MB")
                if result.error:
                    click.echo(f"  Error: {result.error}")

            click.echo(f"\n{'Summary':=^60}")
            click.echo(f"Total: {distribution_result.total_hosts} hosts")
            click.echo(f"Success: {distribution_result.successful}")
            click.echo(f"Failed: {distribution_result.failed}")
            click.echo(
                f"Total transferred: "
                f"{distribution_result.total_bytes_transferred / 1024 / 1024:.2f} MB"
            )
            click.echo(f"Duration: {distribution_result.total_duration:.2f}s")

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise click.ClickException(str(e))


@remote.command(name="scan")
@click.argument("cidr", type=str)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=2,
    help="Ping timeout in seconds (default: 2)",
)
@click.option(
    "--parallel",
    "-p",
    type=int,
    default=20,
    help="Parallel worker count (default: 20)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--output-file",
    type=click.Path(),
    help="Save results to file",
)
def scan_command(
    cidr: str,
    timeout: int,
    parallel: int,
    output: str,
    output_file: Optional[str],
) -> None:
    """Scan network CIDR range for alive hosts."""
    try:
        scanner = NetworkScanner(timeout=timeout, parallel=parallel)
        result = scanner.scan_range(cidr)

        if output == "json":
            data = result.to_dict()
            reporter = JSONReporter()
            if output_file:
                reporter.write(data, Path(output_file))
                click.echo(f"Output saved to {output_file}")
            else:
                click.echo(JSONReporter().format(data))

        else:  # text output
            click.echo(f"\n{'Scan Results for ' + cidr:=^60}")
            click.echo(f"Total hosts: {result.total_hosts}")
            click.echo(f"Alive: {result.alive_hosts}")
            click.echo(f"Dead: {result.dead_hosts}")
            click.echo(f"Duration: {result.duration_seconds:.2f}s\n")

            if result.alive_hosts > 0:
                click.echo(f"{'IP Address':<20} {'Hostname':<30} {'Response (ms)':>12}")
                click.echo("-" * 60)
                for host in result.hosts:
                    if host.is_alive:
                        hostname = (
                            host.hostname[:28] if host.hostname else "(unknown)"
                        )
                        click.echo(
                            f"{host.ip_address:<20} {hostname:<30} "
                            f"{host.response_time_ms:>12.1f}"
                        )

    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise click.ClickException(str(e))
