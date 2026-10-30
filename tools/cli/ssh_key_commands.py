"""Public key validation and authoritative inventory synchronization."""

import json
from pathlib import Path

import click

from tools.remote.ssh_keys import inspect_server, load_servers, validate_public_key


@click.group(name="keys")
def keys():
    """Validar y conciliar llaves públicas SSH según un inventario autorizado."""


@keys.command(name="validate")
@click.argument("public_keys", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
def validate(public_keys):
    """Validar archivos públicos y mostrar huellas SHA256, sin conectar a servidores."""
    try:
        for path in public_keys:
            key = validate_public_key(path)
            click.echo(json.dumps({"file": path, "fingerprint": key.fingerprint}))
    except (OSError, ValueError, TimeoutError) as exc:
        raise click.ClickException(str(exc)) from exc


def inventory_options(function):
    for option in reversed([
        click.option("--hosts-file", required=True, type=click.Path(exists=True, dir_okay=False)),
        click.option("--identity", type=click.Path(exists=True, dir_okay=False), help="Llave privada local de acceso"),
        click.option("--timeout", default=30, type=click.IntRange(1, 300), show_default=True),
    ]):
        function = option(function)
    return function


def run_inventory(hosts_file, identity, timeout, apply=False, allow_empty=False):
    try:
        servers = load_servers(hosts_file)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    failed = False
    for server in servers:
        desired = server.pop("keys")
        report = inspect_server(server, desired, Path(identity) if identity else None,
                                apply=apply, timeout=timeout, allow_empty=allow_empty)
        report["desired_fingerprints"] = [key.fingerprint for key in desired]
        click.echo(json.dumps(report, ensure_ascii=False))
        failed = failed or not report["success"] or (
            not apply and (report.get("missing", 0) > 0 or report.get("extra", 0) > 0)
        )
    if failed:
        raise click.ClickException("Hay diferencias o comprobaciones fallidas; revisar el informe")


@keys.command(name="audit")
@inventory_options
def audit(**kwargs):
    """Leer authorized_keys de cada cuenta y reportar altas y bajas; no escribir."""
    run_inventory(**kwargs)


@keys.command(name="sync")
@inventory_options
@click.option("--apply", is_flag=True, help="Añadir y revocar según el inventario, con respaldo")
@click.option("--allow-empty", is_flag=True, help="Permitir revocar todas las llaves de una cuenta")
def sync(apply, allow_empty, **kwargs):
    """Mostrar el plan por defecto; --apply hace autoritativo el inventario."""
    run_inventory(apply=apply, allow_empty=allow_empty, **kwargs)
