"""
Tests para MonitoringManager.
"""

import json
from unittest.mock import Mock, patch
from tools.monitoring import MonitoringManager, AlertLevel


class TestMonitoringManager:
    """Tests para MonitoringManager."""

    def test_get_system_metrics(self, tmp_path):
        """Test obtener métricas del sistema."""
        manager = MonitoringManager(log_dir=tmp_path)
        metrics = manager.get_system_metrics()
        
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0
        assert metrics.disk_percent >= 0
        assert metrics.network_sent_mb >= 0
        assert metrics.network_recv_mb >= 0
        assert metrics.timestamp is not None

    def test_check_resource_thresholds_pass(self, tmp_path):
        """Test verificación de recursos dentro de umbrales."""
        manager = MonitoringManager(log_dir=tmp_path)
        
        # Umbrales muy altos para que pase
        result = manager.check_resource_thresholds(
            cpu_threshold=99.0,
            memory_threshold=99.0,
            disk_threshold=99.0,
        )
        
        assert result.name == "resource_check"
        assert result.success is True
        assert result.level == AlertLevel.INFO
        assert "within thresholds" in result.message.lower()

    def test_check_resource_thresholds_fail(self, tmp_path):
        """Test verificación de recursos fuera de umbrales."""
        manager = MonitoringManager(log_dir=tmp_path)
        
        # Umbrales muy bajos para que falle
        result = manager.check_resource_thresholds(
            cpu_threshold=0.1,
            memory_threshold=0.1,
            disk_threshold=0.1,
        )
        
        assert result.name == "resource_check"
        assert result.success is False
        assert result.level in [AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]

    def test_check_port_open(self, tmp_path):
        """Test verificación de puerto abierto."""
        manager = MonitoringManager(log_dir=tmp_path)
        
        # Intentar conectar a un puerto conocido (probablemente cerrado localmente)
        # Este test puede fallar si el puerto está abierto
        result = manager.check_port("localhost", 22, timeout=1.0)
        
        assert result.name == "port_check"
        assert result.timestamp is not None
        assert "host" in result.details
        assert "port" in result.details

    @patch("requests.get")
    def test_check_http_success(self, mock_get, tmp_path):
        """Test verificación HTTP exitosa."""
        # Mock de respuesta exitosa
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"OK"
        mock_get.return_value = mock_response
        
        manager = MonitoringManager(log_dir=tmp_path)
        result = manager.check_http("http://example.com", timeout=5.0)
        
        assert result.name == "http_check"
        assert result.success is True
        assert result.level == AlertLevel.INFO
        assert result.details["status_code"] == 200

    @patch("requests.get")
    def test_check_http_wrong_status(self, mock_get, tmp_path):
        """Test verificación HTTP con código incorrecto."""
        # Mock de respuesta con código diferente
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.content = b"Not Found"
        mock_get.return_value = mock_response
        
        manager = MonitoringManager(log_dir=tmp_path)
        result = manager.check_http("http://example.com", timeout=5.0, expected_status=200)
        
        assert result.name == "http_check"
        assert result.success is False
        assert result.level == AlertLevel.WARNING
        assert result.details["status_code"] == 404

    @patch("requests.get")
    def test_check_http_timeout(self, mock_get, tmp_path):
        """Test verificación HTTP con timeout."""
        import requests
        mock_get.side_effect = requests.Timeout("Connection timeout")
        
        manager = MonitoringManager(log_dir=tmp_path)
        result = manager.check_http("http://example.com", timeout=1.0)
        
        assert result.name == "http_check"
        assert result.success is False
        assert result.level == AlertLevel.ERROR
        assert "timeout" in result.message.lower()

    def test_logging(self, tmp_path):
        """Test que los checks se registran en el log."""
        manager = MonitoringManager(log_dir=tmp_path)
        
        # Realizar una verificación
        manager.check_resource_thresholds(
            cpu_threshold=99.0,
            memory_threshold=99.0,
            disk_threshold=99.0,
        )
        
        # Verificar que se creó el log
        assert manager.log_file.exists()
        
        # Leer el log
        with open(manager.log_file, 'r') as f:
            log_line = f.readline()
            log_entry = json.loads(log_line)
        
        assert log_entry["name"] == "resource_check"
        assert "timestamp" in log_entry
        assert "success" in log_entry
        assert "level" in log_entry
        assert "message" in log_entry

    def test_get_recent_logs(self, tmp_path):
        """Test obtener logs recientes."""
        manager = MonitoringManager(log_dir=tmp_path)
        
        # Realizar varias verificaciones
        for _ in range(5):
            manager.check_resource_thresholds(
                cpu_threshold=99.0,
                memory_threshold=99.0,
                disk_threshold=99.0,
            )
        
        # Obtener logs
        logs = manager.get_recent_logs(limit=3)
        
        assert len(logs) == 3
        assert all("timestamp" in log for log in logs)
        assert all("message" in log for log in logs)

    def test_get_recent_logs_empty(self, tmp_path):
        """Test obtener logs cuando no hay ninguno."""
        manager = MonitoringManager(log_dir=tmp_path)
        logs = manager.get_recent_logs()
        
        assert logs == []
