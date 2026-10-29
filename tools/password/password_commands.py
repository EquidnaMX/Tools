"""
CLI commands for password management

Integrates password manager with Tools CLI interface
"""

import asyncio
import click
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from .manager import PasswordManager
from .models import PasswordPolicy, LDAPConfig, NotificationConfig, RotationPolicy

# Global password manager instance
_manager: Optional[PasswordManager] = None


def get_manager(config_file: Optional[str] = None) -> PasswordManager:
    """Get or create password manager instance"""

    global _manager

    if _manager is None:
        # Load config if provided
        policy = PasswordPolicy()
        ldap_config = None
        notification_config = NotificationConfig()
        rotation_policy = RotationPolicy()

        if config_file and Path(config_file).exists():
            config = _load_config(config_file)
            if "policy" in config:
                policy = PasswordPolicy(**config["policy"])
            if "ldap" in config:
                ldap_config = LDAPConfig(**config["ldap"])
            if "notifications" in config:
                notification_config = NotificationConfig(**config["notifications"])
            if "rotation" in config:
                rotation_policy = RotationPolicy(**config["rotation"])

        _manager = PasswordManager(
            policy=policy,
            ldap_config=ldap_config,
            notification_config=notification_config,
            rotation_policy=rotation_policy,
        )

    return _manager


def _load_config(config_file: str) -> dict:
    """Load configuration from YAML or JSON"""

    path = Path(config_file)

    if path.suffix.lower() == ".json":
        with open(path) as f:
            return json.load(f)

    # For YAML, would need pyyaml
    try:
        import yaml

        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        click.echo("⚠️  YAML support requires: pip install pyyaml", err=True)
        return {}


@click.group(name="password")
@click.pass_context
def password_group(ctx):
    """Password management tools"""
    pass


@password_group.command("change")
@click.argument("hosts", nargs=-1, required=True)
@click.option("--username", "-u", required=True, help="Username to change")
@click.option(
    "--old-password",
    "-p",
    default=None,
    help="Current password (will prompt if not provided)",
)
@click.option(
    "--new-password",
    "-n",
    default=None,
    help="New password (will prompt if not provided)",
)
@click.option("--auto-generate", "-g", is_flag=True, help="Auto-generate new password")
@click.option("--dry-run", is_flag=True, help="Simulate without executing")
@click.option(
    "--parallel", "-j", default=3, type=int, help="Parallel jobs (default: 3)"
)
@click.option("--verify/--no-verify", default=True, help="Verify change with SSH login")
@click.option("--ldap/--no-ldap", default=True, help="Sync with LDAP")
@click.option("--notify/--no-notify", default=True, help="Send notifications")
@click.option("--reason", "-r", default="", help="Reason for change (logged in audit)")
@click.option("--config", default=None, help="Configuration file (YAML/JSON)")
def change_password(
    hosts,
    username,
    old_password,
    new_password,
    auto_generate,
    dry_run,
    parallel,
    verify,
    ldap,
    notify,
    reason,
    config,
):
    """
    Change password on multiple hosts

    Example:
        tools password change host1 host2 host3 -u root -g
        tools password change 192.168.1.10 -u admin -p current_pwd -n new_pwd --dry-run
    """

    manager = get_manager(config)

    # Run async operation
    results = asyncio.run(
        manager.change_password(
            hosts=list(hosts),
            username=username,
            old_password=old_password,
            new_password=new_password,
            auto_generate=auto_generate,
            dry_run=dry_run,
            parallel_jobs=parallel,
            verify=verify,
            ldap_sync=ldap,
            notify=notify,
            reason=reason,
        )
    )

    # Check for failures
    failures = [
        h for h, r in results.items() if not r.status.value.startswith("success")
    ]
    if failures:
        click.echo(f"⚠️  Cambios fallidos en {len(failures)} servidor(es)", err=True)
        exit(1)


@password_group.command("generate")
@click.option("--length", "-l", default=16, type=int, help="Password length")
@click.option("--uppercase/--no-uppercase", default=True, help="Include uppercase")
@click.option("--lowercase/--no-lowercase", default=True, help="Include lowercase")
@click.option("--digits/--no-digits", default=True, help="Include digits")
@click.option("--special/--no-special", default=True, help="Include special chars")
@click.option(
    "--count", "-c", default=1, type=int, help="Number of passwords to generate"
)
@click.option("--check", is_flag=True, help="Check strength after generating")
def generate_password(length, uppercase, lowercase, digits, special, count, check):
    """
    Generate secure passwords

    Example:
        tools password generate -l 20 --check -c 5
    """

    manager = get_manager()

    for i in range(count):
        password = manager.generate_password(
            length=length,
            include_uppercase=uppercase,
            include_lowercase=lowercase,
            include_digits=digits,
            include_special=special,
        )

        if check:
            valid, details = manager.validate_password(password)
            score = details.get("score", 0)
            entropy = details.get("entropy_bits", 0)
            click.echo(f"{password}  [Score: {score}/100, Entropy: {entropy:.1f} bits]")
        else:
            click.echo(password)


@password_group.command("validate")
@click.argument("password", default=None, required=False)
@click.option("--config", default=None, help="Configuration file")
def validate_password_cmd(password, config):
    """
    Validate password against policy

    Example:
        tools password validate
        echo "MyP@ssw0rd" | tools password validate -
    """

    if password is None:
        import getpass

        password = getpass.getpass("Contraseña: ")
    elif password == "-":
        # Read from stdin
        password = click.get_text_stream("stdin").read().strip()

    manager = get_manager(config)
    valid, details = manager.validate_password(password)

    status = "✓ Válida" if valid else "✗ Inválida"
    click.echo(f"\n{status}")
    click.echo(f"Puntuación: {details['score']}/100")
    click.echo(f"Entropía: {details['entropy_bits']:.1f} bits")

    if details["errors"]:
        click.echo("\n❌ Errores:")
        for error in details["errors"]:
            click.echo(f"  - {error}")

    if details["warnings"]:
        click.echo("\n⚠️  Advertencias:")
        for warning in details["warnings"]:
            click.echo(f"  - {warning}")

    if details["info"]:
        click.echo("\nℹ️  Información:")
        for info in details["info"]:
            click.echo(f"  - {info}")


@password_group.command("audit")
@click.option("--host", default=None, help="Filter by host")
@click.option("--user", "-u", default=None, help="Filter by username")
@click.option("--operator", "-o", default=None, help="Filter by operator")
@click.option(
    "--status",
    "-s",
    default=None,
    type=click.Choice(["success", "failed", "timeout", "partial"]),
    help="Filter by status",
)
@click.option("--from-date", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--to-date", default=None, help="End date (YYYY-MM-DD)")
@click.option(
    "--format",
    "-f",
    default="table",
    type=click.Choice(["table", "json", "csv"]),
    help="Output format",
)
@click.option("--limit", default=50, type=int, help="Max results")
@click.option("--export", default=None, help="Export to file")
def audit_logs(host, user, operator, status, from_date, to_date, format, limit, export):
    """
    View password change audit logs

    Example:
        tools password audit --host server1 --user root
        tools password audit --status failed --format json --export report.json
    """

    manager = get_manager()

    # Parse dates
    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt = datetime.fromisoformat(to_date) if to_date else None

    # Query audit log
    entries = manager.auditor.query_log(
        from_date=from_dt,
        to_date=to_dt,
        host=host,
        username=user,
        operator=operator,
        status=status,
        limit=limit,
    )

    if not entries:
        click.echo("No se encontraron registros")
        return

    # Format output
    if format == "table":
        click.echo(
            f"\n{'Host':<20} {'Usuario':<15} {'Operador':<15} {'Estado':<12} {'Fecha':<19} {'Duración':<10}"
        )
        click.echo("-" * 100)

        for entry in entries:
            date_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            duration_str = f"{entry.duration:.1f}s" if entry.duration else "N/A"

            click.echo(
                f"{entry.host:<20} {entry.username:<15} {entry.operator:<15} "
                f"{entry.status:<12} {date_str:<19} {duration_str:<10}"
            )

    elif format == "json":
        output = [
            {
                "host": e.host,
                "username": e.username,
                "operator": e.operator,
                "status": e.status,
                "timestamp": e.timestamp.isoformat(),
                "duration": e.duration,
                "method": e.method,
                "ldap_synced": e.ldap_synced,
            }
            for e in entries
        ]

        if export:
            with open(export, "w") as f:
                json.dump(output, f, indent=2)
            click.echo(f"✓ Exportado a {export}")
        else:
            click.echo(json.dumps(output, indent=2))

    elif format == "csv":
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "host",
                "username",
                "operator",
                "status",
                "timestamp",
                "duration",
                "method",
                "ldap_synced",
            ],
        )
        writer.writeheader()

        for entry in entries:
            writer.writerow(
                {
                    "host": entry.host,
                    "username": entry.username,
                    "operator": entry.operator,
                    "status": entry.status,
                    "timestamp": entry.timestamp.isoformat(),
                    "duration": entry.duration,
                    "method": entry.method,
                    "ldap_synced": entry.ldap_synced,
                }
            )

        if export:
            with open(export, "w") as f:
                f.write(output.getvalue())
            click.echo(f"✓ Exportado a {export}")
        else:
            click.echo(output.getvalue())


@password_group.command("status")
@click.option("--config", default=None, help="Configuration file")
def rotation_status(config):
    """
    Check password rotation status

    Example:
        tools password status
    """

    manager = get_manager(config)

    # Get stats
    stats = manager.scheduler.get_rotation_statistics()

    click.echo("\n📊 Estado de Rotaciones de Contraseña")
    click.echo("-" * 50)

    if "total_rotations" in stats:
        click.echo(f"Total rotaciones: {stats['total_rotations']}")

    if "total_hosts" in stats:
        click.echo(f"Servidores bajo rotación: {stats['total_hosts']}")

    if "total_users" in stats:
        click.echo(f"Usuarios bajo rotación: {stats['total_users']}")

    # Get due rotations
    due = manager.scheduler.get_due_rotations()
    if due:
        click.echo(f"\n⚠️  Rotaciones vencidas: {len(due)}")
        for entry in due[:5]:
            click.echo(
                f"   - {entry.host}:{entry.username} (vencida hace {entry.days_until_next * -1} días)"
            )

    # Get upcoming rotations
    upcoming = manager.scheduler.get_upcoming_rotations(days_ahead=7)
    if upcoming:
        click.echo(f"\n📅 Próximas rotaciones (7 días): {len(upcoming)}")
        for entry in upcoming[:5]:
            click.echo(
                f"   - {entry.host}:{entry.username} ({entry.days_until_next} días)"
            )


@password_group.command("rotate")
@click.option("--host", help="Specific host to rotate")
@click.option("--user", "-u", help="Specific user to rotate")
@click.option("--all", is_flag=True, help="Rotate all due entries")
@click.option("--config", default=None, help="Configuration file")
def manual_rotate(host, user, all, config):
    """
    Manually trigger password rotation

    Example:
        tools password rotate --host server1 --user root
        tools password rotate --all
    """

    get_manager(config)

    click.echo("🔄 Iniciando rotaciones manuales...")

    # TODO: Implement manual rotation trigger
    click.echo("⚠️  Funcionalidad en desarrollo")


@password_group.command("init-config")
@click.option(
    "--output", "-o", default="password_config.yaml", help="Output config file"
)
@click.option(
    "--format",
    "-f",
    default="yaml",
    type=click.Choice(["yaml", "json"]),
    help="Config format",
)
def init_config(output, format):
    """
    Generate template configuration file

    Example:
        tools password init-config --output my_config.yaml
    """

    if format == "yaml":
        template = """# Password Management Configuration

policy:
  min_length: 12
  max_length: 128
  require_uppercase: true
  require_lowercase: true
  require_digits: true
  require_special: true
  excluded_terms:
    - password
    - admin
    - root
    - server
    - 123456
  password_history: 5
  password_age_days: 90

ldap:
  enabled: false
  server_uri: "ldap://ldap.example.com"
  bind_dn: "cn=admin,dc=example,dc=com"
  base_dn: "dc=example,dc=com"
  use_tls: true
  use_ssl: false

notifications:
  enabled: true
  smtp:
    server: "smtp.gmail.com"
    port: 587
    use_tls: true
    username: "noreply@example.com"
    email_recipients:
      - "admin@example.com"
  webhooks:
    - url: "https://hooks.example.com/password-changes"
      retry_count: 3
      timeout_seconds: 10

rotation:
  enabled: false
  interval_days: 30
  schedule_hour: 2
  schedule_minute: 0
"""
    else:
        import json

        template = json.dumps(
            {
                "policy": {
                    "min_length": 12,
                    "max_length": 128,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_digits": True,
                    "require_special": True,
                    "excluded_terms": ["password", "admin", "root", "server", "123456"],
                    "password_history": 5,
                    "password_age_days": 90,
                },
                "ldap": {
                    "enabled": False,
                    "server_uri": "ldap://ldap.example.com",
                    "bind_dn": "cn=admin,dc=example,dc=com",
                    "base_dn": "dc=example,dc=com",
                },
                "notifications": {
                    "enabled": True,
                    "smtp": {"server": "smtp.gmail.com", "port": 587},
                    "webhooks": [],
                },
            },
            indent=2,
        )

    with open(output, "w") as f:
        f.write(template)

    click.echo(f"✓ Archivo de configuración creado: {output}")
    click.echo("⚠️  Recuerda: Actualiza las credenciales y URLs antes de usar")
