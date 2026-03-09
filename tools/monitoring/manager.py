"""
Gestor de monitoreo y alertas.

Proporciona funcionalidades para:
- Monitorear recursos del sistema (CPU, memoria, disco)
- Verificar disponibilidad de servicios
- Generar alertas basadas en umbrales
- Registrar eventos de monitoreo
"""

import psutil
import time
import socket
import requests
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional
import json


class AlertLevel(Enum):
    """Niveles de alerta."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ResourceMetrics:
    """Métricas de recursos del sistema."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_sent_mb: float
    network_recv_mb: float


@dataclass
class CheckResult:
    """Resultado de una verificación de monitoreo."""
    name: str
    timestamp: datetime
    success: bool
    level: AlertLevel
    message: str
    details: Dict[str, Any]


class MonitoringManager:
    """Gestor de monitoreo y alertas."""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Inicializa el gestor de monitoreo.

        Args:
            log_dir: Directorio para almacenar logs de monitoreo
        """
        self.log_dir = Path(log_dir) if log_dir else Path.home() / ".tools" / "monitoring"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "monitoring.log"

    def get_system_metrics(self) -> ResourceMetrics:
        """
        Obtiene métricas actuales del sistema.

        Returns:
            ResourceMetrics con las métricas actuales
        """
        net_io = psutil.net_io_counters()
        
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=psutil.cpu_percent(interval=1),
            memory_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage('/').percent,
            network_sent_mb=net_io.bytes_sent / (1024 * 1024),
            network_recv_mb=net_io.bytes_recv / (1024 * 1024),
        )

    def check_resource_thresholds(
        self,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 80.0,
        disk_threshold: float = 90.0,
    ) -> CheckResult:
        """
        Verifica que los recursos del sistema estén dentro de umbrales.

        Args:
            cpu_threshold: Umbral de CPU en porcentaje
            memory_threshold: Umbral de memoria en porcentaje
            disk_threshold: Umbral de disco en porcentaje

        Returns:
            CheckResult con el resultado de la verificación
        """
        metrics = self.get_system_metrics()
        
        issues = []
        level = AlertLevel.INFO
        
        if metrics.cpu_percent > cpu_threshold:
            issues.append(f"CPU at {metrics.cpu_percent}% (threshold: {cpu_threshold}%)")
            level = AlertLevel.WARNING if metrics.cpu_percent < 95 else AlertLevel.CRITICAL
        
        if metrics.memory_percent > memory_threshold:
            issues.append(f"Memory at {metrics.memory_percent}% (threshold: {memory_threshold}%)")
            if level.value in ["info", "warning"]:
                level = AlertLevel.WARNING if metrics.memory_percent < 95 else AlertLevel.CRITICAL
        
        if metrics.disk_percent > disk_threshold:
            issues.append(f"Disk at {metrics.disk_percent}% (threshold: {disk_threshold}%)")
            if level == AlertLevel.INFO:
                level = AlertLevel.ERROR
        
        success = len(issues) == 0
        message = "All resources within thresholds" if success else "; ".join(issues)
        
        result = CheckResult(
            name="resource_check",
            timestamp=metrics.timestamp,
            success=success,
            level=level,
            message=message,
            details={
                "cpu_percent": metrics.cpu_percent,
                "memory_percent": metrics.memory_percent,
                "disk_percent": metrics.disk_percent,
            },
        )
        
        self._log_check(result)
        return result

    def check_port(self, host: str, port: int, timeout: float = 5.0) -> CheckResult:
        """
        Verifica si un puerto está abierto y accesible.

        Args:
            host: Host a verificar
            port: Puerto a verificar
            timeout: Timeout en segundos

        Returns:
            CheckResult con el resultado de la verificación
        """
        timestamp = datetime.now()
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            success = result == 0
            message = f"Port {port} is {'open' if success else 'closed'} on {host}"
            level = AlertLevel.INFO if success else AlertLevel.ERROR
            
            check_result = CheckResult(
                name="port_check",
                timestamp=timestamp,
                success=success,
                level=level,
                message=message,
                details={"host": host, "port": port, "result_code": result},
            )
            
        except socket.gaierror as e:
            check_result = CheckResult(
                name="port_check",
                timestamp=timestamp,
                success=False,
                level=AlertLevel.ERROR,
                message=f"Failed to resolve host {host}: {e}",
                details={"host": host, "port": port, "error": str(e)},
            )
        except Exception as e:
            check_result = CheckResult(
                name="port_check",
                timestamp=timestamp,
                success=False,
                level=AlertLevel.ERROR,
                message=f"Error checking port: {e}",
                details={"host": host, "port": port, "error": str(e)},
            )
        
        self._log_check(check_result)
        return check_result

    def check_http(self, url: str, timeout: float = 10.0, expected_status: int = 200) -> CheckResult:
        """
        Verifica la disponibilidad de un endpoint HTTP.

        Args:
            url: URL a verificar
            timeout: Timeout en segundos
            expected_status: Código de estado HTTP esperado

        Returns:
            CheckResult con el resultado de la verificación
        """
        timestamp = datetime.now()
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            response_time = (time.time() - start_time) * 1000  # en ms
            
            success = response.status_code == expected_status
            level = AlertLevel.INFO if success else AlertLevel.WARNING
            message = (
                f"HTTP {response.status_code} from {url} "
                f"(expected {expected_status}, {response_time:.0f}ms)"
            )
            
            check_result = CheckResult(
                name="http_check",
                timestamp=timestamp,
                success=success,
                level=level,
                message=message,
                details={
                    "url": url,
                    "status_code": response.status_code,
                    "response_time_ms": round(response_time, 2),
                    "content_length": len(response.content),
                },
            )
            
        except requests.Timeout:
            check_result = CheckResult(
                name="http_check",
                timestamp=timestamp,
                success=False,
                level=AlertLevel.ERROR,
                message=f"Timeout accessing {url} (>{timeout}s)",
                details={"url": url, "timeout": timeout},
            )
        except requests.RequestException as e:
            check_result = CheckResult(
                name="http_check",
                timestamp=timestamp,
                success=False,
                level=AlertLevel.ERROR,
                message=f"Error accessing {url}: {e}",
                details={"url": url, "error": str(e)},
            )
        
        self._log_check(check_result)
        return check_result

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene los registros de monitoreo recientes.

        Args:
            limit: Número máximo de registros a devolver

        Returns:
            Lista de registros de monitoreo
        """
        if not self.log_file.exists():
            return []
        
        logs = []
        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        
        # Devolver los más recientes
        return logs[-limit:]

    def _log_check(self, result: CheckResult) -> None:
        """
        Registra el resultado de una verificación.

        Args:
            result: Resultado a registrar
        """
        log_entry = {
            "name": result.name,
            "timestamp": result.timestamp.isoformat(),
            "success": result.success,
            "level": result.level.value,
            "message": result.message,
            "details": result.details,
        }
        
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
