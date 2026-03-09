"""CLI commands for mail server management.

Provides commands for mail server auditing, domain health checks,
and DNS validation.
"""

import sys
import json
from pathlib import Path
from typing import Optional

import click

from tools.core.logger import get_logger, setup_logging
from tools.mail.auditor import MailAuditor
from tools.mail.domain_health import DomainHealthChecker
from tools.mail.dns_validator import DNSValidator


logger = get_logger("cli.mail")


@click.group(name="mail")
def mail():
    """Mail server management commands."""
    pass


@mail.command(name="audit")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: mail_audit_<timestamp>.json)",
)
@click.option(
    "--ptr-target",
    type=str,
    help="Expected PTR record value",
)
@click.option(
    "--selector",
    type=str,
    default="default",
    help="DKIM selector (default: default)",
)
@click.option(
    "--domains",
    "-d",
    multiple=True,
    help="Specific domains to audit (auto-discovers if not specified)",
)
@click.option(
    "--no-rbls",
    is_flag=True,
    help="Skip RBL reputation checks",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def audit_command(
    output: Optional[str],
    ptr_target: Optional[str],
    selector: str,
    domains: tuple,
    no_rbls: bool,
    format: str,
    verbose: bool,
):
    """Perform comprehensive mail server audit.
    
    Audits the mail server including:
    - Domain discovery from Postfix, OpenDKIM, Sympa
    - Service status monitoring
    - DNS record validation (MX, SPF, DKIM, DMARC, PTR)
    - RBL reputation checks
    - Sympa configuration validation
    
    Examples:
        # Full audit with auto-discovery
        tools mail audit
        
        # Audit specific domains
        tools mail audit -d example.com -d test.com
        
        # Audit with PTR validation
        tools mail audit --ptr-target mail.example.com
        
        # Skip RBL checks
        tools mail audit --no-rbls
    """
    setup_logging(verbose=verbose)
    
    logger.info("Starting mail server audit...")
    
    # Create auditor
    auditor = MailAuditor(
        ptr_target=ptr_target,
        dkim_selector=selector,
        include_rbls=not no_rbls,
    )
    
    # Run audit
    try:
        domains_list = list(domains) if domains else None
        report = auditor.audit_server(domains=domains_list)
    except Exception as exc:
        logger.error(f"Audit failed: {exc}")
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    
    # Generate output
    if format == "json":
        report_dict = report.to_dict()
        
        if output:
            output_path = Path(output)
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"mail_audit_{timestamp}.json")
        
        output_path.write_text(json.dumps(report_dict, indent=2))
        click.echo(f"✅ Audit report saved to: {output_path}")
        
    else:  # text format
        click.echo(f"\n{'=' * 70}")
        click.echo("MAIL SERVER AUDIT REPORT")
        click.echo(f"{'='*70}\n")
        
        click.echo(f"Server: {report.server_hostname} ({report.server_ip})")
        click.echo(f"PTR: {report.ptr_record} (status: {report.ptr_status})")
        click.echo()
        
        # Services
        click.echo("Services:")
        active_services = sum(1 for s in report.services.values() if s.is_running)
        click.echo(f"  Active: {active_services}/{len(report.services)}")
        
        for name, status in sorted(report.services.items()):
            icon = "✓" if status.is_running else "✗"
            click.echo(f"  {icon} {name}: {status.state.value}")
        
        click.echo()
        
        # Domains
        click.echo(f"Domains ({len(report.domains)}):")
        for domain_result in report.domains:
            domain = domain_result.domain
            dns = domain_result.dns_validation
            
            if dns:
                mx_icon = "✓" if dns.has_mx else "✗"
                spf_icon = "✓" if dns.has_spf else "✗"
                dkim_icon = "✓" if dns.has_dkim else "✗"
                dmarc_icon = "✓" if dns.has_dmarc else "✗"
                
                click.echo(
                    f"  {domain}: MX{mx_icon} SPF{spf_icon} "
                    f"DKIM{dkim_icon} DMARC{dmarc_icon}"
                )
        
        click.echo()
        
        # Reputation
        if report.reputation:
            click.echo("Reputation:")
            for rbl_check in report.reputation:
                status_icon = "✗" if rbl_check.listed else "✓"
                status_text = "LISTED" if rbl_check.listed else "clean"
                click.echo(f"  {status_icon} {rbl_check.rbl_name}: {status_text}")
            click.echo()
        
        # Errors
        if report.errors:
            click.echo("Errors:")
            for error in report.errors:
                click.echo(f"  • {error}")
            click.echo()


@mail.command(name="check-domain")
@click.argument("domain", required=False)
@click.option(
    "--selector",
    type=str,
    help="DKIM selector (auto-detects if not specified)",
)
@click.option(
    "--no-connectivity",
    is_flag=True,
    help="Skip SMTP connectivity checks",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def check_domain_command(
    domain: Optional[str],
    selector: Optional[str],
    no_connectivity: bool,
    format: str,
    verbose: bool,
):
    """Check health of mail domain(s).
    
    Performs quick health checks including:
    - DNS record validation (MX, SPF, DKIM, DMARC)
    - SMTP connectivity tests
    - DKIM selector auto-detection from OpenDKIM
    
    If DOMAIN is not specified, checks all domains from OpenDKIM configuration.
    
    Examples:
        # Check single domain
        tools mail check-domain example.com
        
        # Check with specific DKIM selector
        tools mail check-domain example.com --selector mail
        
        # Check all domains from OpenDKIM
        tools mail check-domain
        
        # JSON output
        tools mail check-domain example.com --format json
    """
    setup_logging(verbose=verbose)
    
    # Create health checker
    checker = DomainHealthChecker(
        check_connectivity=not no_connectivity,
    )
    
    # Check domain(s)
    if domain:
        # Single domain
        health = checker.check_domain_health(domain, selector)
        results = [health]
    else:
        # Auto-discover from OpenDKIM
        selectors = checker.parse_opendkim_signing_table()
        
        if not selectors:
            selectors = checker.parse_opendkim_key_table()
        
        if not selectors:
            click.echo("No domains found in OpenDKIM configuration", err=True)
            sys.exit(1)
        
        domains = sorted(selectors.keys())
        logger.info(f"Checking {len(domains)} domains from OpenDKIM")
        
        results = checker.check_multiple_domains(domains, selectors)
    
    # Output results
    if format == "json":
        output = {
            "domains": [r.to_dict() for r in results],
            "summary": checker.get_summary(results),
        }
        click.echo(json.dumps(output, indent=2))
        
    else:  # text format
        click.echo(f"\n{'=' * 70}")
        click.echo("DOMAIN HEALTH CHECK")
        click.echo(f"{'='*70}\n")
        
        for health in results:
            score_color = "green" if health.score >= 80 else "yellow" if health.score >= 50 else "red"
            
            click.echo(f"Domain: {health.domain}")
            click.echo(click.style(f"  Score: {health.score}/100", fg=score_color, bold=True))
            click.echo(f"  Selector: {health.selector}")
            
            # Checks
            mx_icon = "✓" if health.has_mx else "✗"
            spf_icon = "✓" if health.has_spf else "✗"
            dkim_icon = "✓" if health.has_dkim else "✗"
            dmarc_icon = "✓" if health.has_dmarc else "✗"
            
            click.echo(f"  Checks: MX{mx_icon} SPF{spf_icon} DKIM{dkim_icon} DMARC{dmarc_icon}")
            
            if health.mx_hosts:
                click.echo(f"  MX Hosts: {', '.join(health.mx_hosts)}")
            
            if health.connectivity:
                reachable = sum(1 for c in health.connectivity if c.reachable)
                click.echo(f"  Connectivity: {reachable}/{len(health.connectivity)} reachable")
            
            if health.issues:
                click.echo("  Issues:")
                for issue in health.issues:
                    click.echo(f"    • {issue}")
            
            click.echo()
        
        # Summary
        if len(results) > 1:
            summary = checker.get_summary(results)
            click.echo(f"Summary: {summary['total_domains']} domains checked")
            click.echo(
                f"  Healthy: {summary['healthy']} | "
                f"Warnings: {summary['warnings']} | "
                f"Critical: {summary['critical']}"
            )
            click.echo(f"  Average Score: {summary['average_score']}/100")
            click.echo()


@mail.command(name="validate-dns")
@click.argument("domain")
@click.option(
    "--selector",
    type=str,
    default="default",
    help="DKIM selector",
)
@click.option(
    "--ptr",
    type=str,
    help="Expected PTR value",
)
@click.option(
    "--server-ip",
    type=str,
    help="Server IP for PTR validation",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def validate_dns_command(
    domain: str,
    selector: str,
    ptr: Optional[str],
    server_ip: Optional[str],
    format: str,
    verbose: bool,
):
    """Validate DNS records for a mail domain.
    
    Validates all required DNS records for mail delivery:
    - MX records
    - A record for mail.domain
    - SPF record
    - DKIM record
    - DMARC record
    - PTR record (if server IP provided)
    
    Examples:
        # Basic DNS validation
        tools mail validate-dns example.com
        
        # With DKIM selector
        tools mail validate-dns example.com --selector mail
        
        # With PTR validation
        tools mail validate-dns example.com --server-ip 1.2.3.4 --ptr mail.example.com
    """
    setup_logging(verbose=verbose)
    
    # Create validator
    validator = DNSValidator(dkim_selector=selector)
    
    # Validate domain
    validation = validator.validate_domain(
        domain=domain,
        selector=selector,
        expected_ptr=ptr,
        server_ip=server_ip,
    )
    
    # Output results
    if format == "json":
        click.echo(json.dumps(validation.to_dict(), indent=2))
        
    else:  # text format
        click.echo(f"\nDNS Validation for: {domain}")
        click.echo(f"{'='*70}\n")
        
        # MX Records
        click.echo("MX Records:")
        if validation.mx_records:
            for mx in validation.mx_records:
                click.echo(f"  {mx}")
        else:
            click.echo(click.style("  ✗ No MX records found", fg="red"))
        click.echo()
        
        # A Record
        click.echo(f"A Record (mail.{domain}):")
        if validation.a_record:
            click.echo(f"  {validation.a_record}")
        else:
            click.echo(click.style("  ✗ No A record found", fg="yellow"))
        click.echo()
        
        # SPF
        click.echo("SPF Record:")
        if validation.spf_record:
            click.echo(f"  {validation.spf_record}")
        else:
            click.echo(click.style("  ✗ No SPF record found", fg="red"))
        click.echo()
        
        # DKIM
        click.echo(f"DKIM Record ({selector}._domainkey.{domain}):")
        if validation.dkim_record:
            # Truncate if too long
            dkim_display = validation.dkim_record[:100]
            if len(validation.dkim_record) > 100:
                dkim_display += "..."
            click.echo(f"  {dkim_display}")
        else:
            click.echo(click.style("  ✗ No DKIM record found", fg="red"))
        click.echo()
        
        # DMARC
        click.echo("DMARC Record:")
        if validation.dmarc_record:
            click.echo(f"  {validation.dmarc_record}")
        else:
            click.echo(click.style("  ✗ No DMARC record found", fg="yellow"))
        click.echo()
        
        # PTR
        if server_ip:
            click.echo(f"PTR Record ({server_ip}):")
            if validation.ptr_record:
                if validation.ptr_matches:
                    click.echo(click.style(f"  ✓ {validation.ptr_record}", fg="green"))
                else:
                    click.echo(
                        click.style(
                            f"  ✗ {validation.ptr_record} (expected: {ptr})",
                            fg="red"
                        )
                    )
            else:
                click.echo(click.style("  ✗ No PTR record found", fg="red"))
            click.echo()
        
        # Errors summary
        if validation.errors:
            click.echo(click.style("Validation Errors:", fg="red", bold=True))
            for error in validation.errors:
                click.echo(f"  • {error}")
        else:
            click.echo(click.style("✓ All validations passed", fg="green", bold=True))
        
        click.echo()


if __name__ == "__main__":
    mail()
