"""
Comandos CLI para monitoreo y alertas.
"""

import click
import time
from pathlib import Path
from tools.monitoring import MonitoringManager, AlertLevel


@click.group()
def monitoring():
    """Comandos de monitoreo y alertas."""
    pass


@monitoring.command(name="check-resources")
@click.option(
    "--cpu-threshold",
    type=float,
    default=80.0,
    help="Umbral de CPU en porcentaje (default: 80)",
)
@click.option(
    "--memory-threshold",
    type=float,
    default=80.0,
    help="Umbral de memoria en porcentaje (default: 80)",
)
@click.option(
    "--disk-threshold",
    type=float,
    default=90.0,
    help="Umbral de disco en porcentaje (default: 90)",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directorio para logs de monitoreo",
)
def check_resources(cpu_threshold, memory_threshold, disk_threshold, log_dir):
    """Verifica recursos del sistema contra umbrales."""
    manager = MonitoringManager(log_dir=log_dir)
    result = manager.check_resource_thresholds(
        cpu_threshold=cpu_threshold,
        memory_threshold=memory_threshold,
        disk_threshold=disk_threshold,
    )
    
    # Color según el nivel
    color = {
        AlertLevel.INFO: "green",
        AlertLevel.WARNING: "yellow",
        AlertLevel.ERROR: "red",
        AlertLevel.CRITICAL: "red",
    }.get(result.level, "white")
    
    click.secho(f"[{result.level.value.upper()}] {result.message}", fg=color, bold=True)
    
    if result.details:
        click.echo("\nDetalles:")
        for key, value in result.details.items():
            click.echo(f"  {key}: {value}")
    
    # Exit code según el resultado
    if not result.success:
        raise click.Abort()


@monitoring.command(name="check-port")
@click.argument("host")
@click.argument("port", type=int)
@click.option(
    "--timeout",
    type=float,
    default=5.0,
    help="Timeout en segundos (default: 5.0)",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directorio para logs de monitoreo",
)
def check_port(host, port, timeout, log_dir):
    """Verifica si un puerto está abierto y accesible."""
    manager = MonitoringManager(log_dir=log_dir)
    result = manager.check_port(host, port, timeout=timeout)
    
    color = "green" if result.success else "red"
    click.secho(f"[{result.level.value.upper()}] {result.message}", fg=color, bold=True)
    
    if not result.success:
        raise click.Abort()


@monitoring.command(name="check-http")
@click.argument("url")
@click.option(
    "--timeout",
    type=float,
    default=10.0,
    help="Timeout en segundos (default: 10.0)",
)
@click.option(
    "--expected-status",
    type=int,
    default=200,
    help="Código de estado HTTP esperado (default: 200)",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directorio para logs de monitoreo",
)
def check_http(url, timeout, expected_status, log_dir):
    """Verifica la disponibilidad de un endpoint HTTP."""
    manager = MonitoringManager(log_dir=log_dir)
    result = manager.check_http(url, timeout=timeout, expected_status=expected_status)
    
    color = "green" if result.success else "yellow"
    click.secho(f"[{result.level.value.upper()}] {result.message}", fg=color, bold=True)
    
    if result.details:
        click.echo("\nDetalles:")
        for key, value in result.details.items():
            if key != "error":  # No mostrar error en detalles si ya está en mensaje
                click.echo(f"  {key}: {value}")
    
    if not result.success:
        raise click.Abort()


@monitoring.command(name="logs")
@click.option(
    "--limit",
    type=int,
    default=20,
    help="Número de registros a mostrar (default: 20)",
)
@click.option(
    "--level",
    type=click.Choice(["info", "warning", "error", "critical"], case_sensitive=False),
    help="Filtrar por nivel de alerta",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directorio de logs de monitoreo",
)
def show_logs(limit, level, log_dir):
    """Muestra logs de monitoreo recientes."""
    manager = MonitoringManager(log_dir=log_dir)
    logs = manager.get_recent_logs(limit=limit)
    
    if not logs:
        click.echo("No hay logs de monitoreo disponibles.")
        return
    
    # Filtrar por nivel si se especifica
    if level:
        logs = [log for log in logs if log.get("level") == level.lower()]
    
    if not logs:
        click.echo(f"No hay logs con nivel '{level}'.")
        return
    
    for log in logs:
        timestamp = log.get("timestamp", "")
        level_str = log.get("level", "info").upper()
        message = log.get("message", "")
        success = log.get("success", False)
        
        # Color según nivel
        color = {
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red",
        }.get(level_str, "white")
        
        status_icon = "✓" if success else "✗"
        click.secho(
            f"{timestamp} [{level_str}] {status_icon} {message}",
            fg=color,
        )


@monitoring.command(name="watch")
@click.option(
    "--interval",
    type=int,
    default=5,
    help="Intervalo en segundos entre verificaciones (default: 5)",
)
@click.option(
    "--cpu-threshold",
    type=float,
    default=80.0,
    help="Umbral de CPU en porcentaje (default: 80)",
)
@click.option(
    "--memory-threshold",
    type=float,
    default=80.0,
    help="Umbral de memoria en porcentaje (default: 80)",
)
@click.option(
    "--disk-threshold",
    type=float,
    default=90.0,
    help="Umbral de disco en porcentaje (default: 90)",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directorio para logs de monitoreo",
)
def watch_resources(interval, cpu_threshold, memory_threshold, disk_threshold, log_dir):
    """Monitorea recursos del sistema continuamente."""
    manager = MonitoringManager(log_dir=log_dir)
    
    click.echo(f"Monitoreando recursos cada {interval}s. Presiona Ctrl+C para detener.\n")
    
    try:
        while True:
            result = manager.check_resource_thresholds(
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                disk_threshold=disk_threshold,
            )
            
            # Color según el nivel
            color = {
                AlertLevel.INFO: "green",
                AlertLevel.WARNING: "yellow",
                AlertLevel.ERROR: "red",
                AlertLevel.CRITICAL: "red",
            }.get(result.level, "white")
            
            timestamp = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            status = "✓" if result.success else "✗"
            
            click.secho(
                f"{timestamp} [{result.level.value.upper()}] {status} "
                f"CPU: {result.details['cpu_percent']:.1f}% | "
                f"MEM: {result.details['memory_percent']:.1f}% | "
                f"DISK: {result.details['disk_percent']:.1f}%",
                fg=color,
            )
            
            if not result.success:
                click.secho(f"  ⚠ {result.message}", fg=color)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        click.echo("\n\nMonitoreo detenido.")
