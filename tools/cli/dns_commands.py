"""CLI commands for DNS management."""

import json
from pathlib import Path
from typing import Optional

import click

from tools.core.logger import get_logger, setup_logging
from tools.dns.installer import DNSInstaller
from tools.dns.ns_fixer import DNSNSFixer, NSFixMode
from tools.dns.replication_checker import DNSReplicationChecker


logger = get_logger("cli.dns")


@click.group(name="dns")
def dns():
    """DNS management commands."""
    pass


@dns.command(name="check-replication")
@click.option("--master-ip", required=True, help="Master DNS IP")
@click.option("--slave-ip", required=True, help="Slave DNS IP")
@click.option("--pdns-control", default="pdns_control", help="pdns_control command")
@click.option("--ssh-slave", help="SSH user@host for slave (for retransfer)")
@click.option("--no-retransfer", is_flag=True, help="Disable automatic retransfer")
@click.option("--output", "output_path", type=click.Path(), help="Write JSON report to file")
@click.option("--verbose", "verbose", is_flag=True, help="Verbose logging")
def check_replication_command(
    master_ip: str,
    slave_ip: str,
    pdns_control: str,
    ssh_slave: Optional[str],
    no_retransfer: bool,
    output_path: Optional[str],
    verbose: bool,
):
    """Check DNS zone replication status between master and slave."""
    setup_logging(verbose=verbose)

    checker = DNSReplicationChecker(
        master_ip=master_ip,
        slave_ip=slave_ip,
        pdns_control_cmd=pdns_control,
        ssh_slave=ssh_slave,
        retry_retransfer=not no_retransfer,
    )

    results = checker.check_replication()
    summary = checker.get_summary(results)

    payload = {
        "master_ip": master_ip,
        "slave_ip": slave_ip,
        "summary": summary,
        "zones": [r.to_dict() for r in results],
    }

    if output_path:
        Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        click.echo(f"Report written to: {output_path}")
        return

    click.echo(f"Total zones: {summary['total_zones']}")
    click.echo(
        f"OK: {summary['ok']} | DESYNC: {summary['desync']} | "
        f"ERR(master): {summary['error_master']} | ERR(slave): {summary['error_slave']}"
    )

    for item in results:
        click.echo(
            f"- {item.zone}: {item.status.value} "
            f"(master={item.master_serial or '-'} slave={item.slave_serial or '-'})"
        )


@dns.command(name="fix-ns")
@click.option("--ns1", required=True, help="Primary NS (FQDN)")
@click.option("--ns2", required=True, help="Secondary NS (FQDN)")
@click.option("--ttl", default=3600, type=int, help="NS record TTL")
@click.option(
    "--mode",
    type=click.Choice([NSFixMode.ENFORCE.value, NSFixMode.APPEND.value]),
    default=NSFixMode.ENFORCE.value,
    help="NS fix mode",
)
@click.option("--pdnsutil", default="pdnsutil", help="pdnsutil command")
@click.option("--pdns-control", default="pdns_control", help="pdns_control command")
@click.option("--output", "output_path", type=click.Path(), help="Write JSON report to file")
@click.option("--verbose", "verbose", is_flag=True, help="Verbose logging")
def fix_ns_command(
    ns1: str,
    ns2: str,
    ttl: int,
    mode: str,
    pdnsutil: str,
    pdns_control: str,
    output_path: Optional[str],
    verbose: bool,
):
    """Fix missing or incorrect NS records in PowerDNS zones."""
    setup_logging(verbose=verbose)

    fixer = DNSNSFixer(
        ns1=ns1,
        ns2=ns2,
        ttl=ttl,
        mode=NSFixMode(mode),
        pdnsutil_cmd=pdnsutil,
        pdns_control_cmd=pdns_control,
    )

    results = fixer.fix_all_zones()
    summary = fixer.get_summary(results)

    payload = {
        "summary": summary,
        "results": [r.to_dict() for r in results],
    }

    if output_path:
        Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        click.echo(f"Report written to: {output_path}")
        return

    click.echo(
        f"Mode={summary['mode']} | changed={summary['changed']} "
        f"unchanged={summary['unchanged']} failed={summary['failed']}"
    )

    for result in results:
        click.echo(f"- {result.zone}: {result.status}")


@dns.group(name="install")
def install_group():
    """Install DNS server components."""
    pass


@install_group.command(name="bind9-slave")
@click.option("--zone", required=True, help="Zone name")
@click.option("--master-ip", required=True, help="Master DNS IP")
@click.option("--dry-run", is_flag=True, help="Do not execute commands")
def install_bind9_slave_command(zone: str, master_ip: str, dry_run: bool):
    """Install and configure BIND9 slave."""
    installer = DNSInstaller(dry_run=dry_run)
    report = installer.install_bind9_slave(zone=zone, master_ip=master_ip)

    click.echo(
        f"Target={report.target} total={len(report.steps)} "
        f"ok={sum(1 for s in report.steps if s.success)} "
        f"failed={sum(1 for s in report.steps if not s.success)}"
    )


@install_group.command(name="pdns-master")
@click.option("--slave-ip", required=True, help="Slave DNS IP")
@click.option("--db-root-password", required=True, help="MySQL root password")
@click.option("--db-pdns-password", required=True, help="PowerDNS DB password")
@click.option("--api-key", default="supersecreta", help="PowerDNS API key")
@click.option("--dry-run", is_flag=True, help="Do not execute commands")
def install_pdns_master_command(
    slave_ip: str,
    db_root_password: str,
    db_pdns_password: str,
    api_key: str,
    dry_run: bool,
):
    """Install and configure PowerDNS master."""
    installer = DNSInstaller(dry_run=dry_run)
    report = installer.install_pdns_master(
        slave_ip=slave_ip,
        db_root_password=db_root_password,
        db_pdns_password=db_pdns_password,
        api_key=api_key,
    )

    click.echo(
        f"Target={report.target} total={len(report.steps)} "
        f"ok={sum(1 for s in report.steps if s.success)} "
        f"failed={sum(1 for s in report.steps if not s.success)}"
    )
