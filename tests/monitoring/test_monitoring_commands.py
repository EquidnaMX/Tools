"""
Tests para comandos CLI de monitoreo.
"""

from click.testing import CliRunner
from unittest.mock import patch, Mock
from tools.cli.monitoring_commands import monitoring


class TestMonitoringCommands:
    """Tests para comandos CLI de monitoreo."""

    def test_check_resources_success(self, tmp_path):
        """Test comando check-resources exitoso."""
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            [
                "check-resources",
                "--cpu-threshold", "99",
                "--memory-threshold", "99",
                "--disk-threshold", "99",
                "--log-dir", str(tmp_path),
            ],
        )
        
        assert result.exit_code == 0
        assert "INFO" in result.output or "within thresholds" in result.output.lower()

    def test_check_resources_failure(self, tmp_path):
        """Test comando check-resources con fallo."""
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            [
                "check-resources",
                "--cpu-threshold", "0.1",
                "--memory-threshold", "0.1",
                "--disk-threshold", "0.1",
                "--log-dir", str(tmp_path),
            ],
        )
        
        assert result.exit_code != 0

    def test_check_port(self, tmp_path):
        """Test comando check-port."""
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            [
                "check-port",
                "localhost",
                "9999",  # Puerto probablemente cerrado
                "--timeout", "1.0",
                "--log-dir", str(tmp_path),
            ],
        )
        
        # El puerto probablemente estará cerrado
        assert "localhost" in result.output or "port" in result.output.lower()

    @patch("requests.get")
    def test_check_http_success(self, mock_get, tmp_path):
        """Test comando check-http exitoso."""
        # Mock de respuesta exitosa
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"OK"
        mock_get.return_value = mock_response
        
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            [
                "check-http",
                "http://example.com",
                "--timeout", "5.0",
                "--log-dir", str(tmp_path),
            ],
        )
        
        assert result.exit_code == 0
        assert "200" in result.output or "INFO" in result.output

    @patch("requests.get")
    def test_check_http_failure(self, mock_get, tmp_path):
        """Test comando check-http con fallo."""
        # Mock de respuesta con error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = b"Error"
        mock_get.return_value = mock_response
        
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            [
                "check-http",
                "http://example.com",
                "--expected-status", "200",
                "--log-dir", str(tmp_path),
            ],
        )
        
        assert result.exit_code != 0
        assert "500" in result.output or "WARNING" in result.output

    def test_show_logs_empty(self, tmp_path):
        """Test comando logs sin registros."""
        runner = CliRunner()
        result = runner.invoke(
            monitoring,
            ["logs", "--log-dir", str(tmp_path)],
        )
        
        assert result.exit_code == 0
        assert "No hay logs" in result.output or "disponibles" in result.output

    def test_show_logs_with_data(self, tmp_path):
        """Test comando logs con registros."""
        # Primero crear algunos logs
        runner = CliRunner()
        runner.invoke(
            monitoring,
            [
                "check-resources",
                "--cpu-threshold", "99",
                "--log-dir", str(tmp_path),
            ],
        )
        
        # Listar los logs
        result = runner.invoke(
            monitoring,
            ["logs", "--limit", "10", "--log-dir", str(tmp_path)],
        )
        
        assert result.exit_code == 0
        # Verificar que hay contenido en la salida (sin importar el nivel)
        assert len(result.output) > 0
        assert "2026" in result.output or "202" in result.output  # Año en timestamp

    def test_monitoring_group(self):
        """Test que el grupo de comandos funciona."""
        runner = CliRunner()
        result = runner.invoke(monitoring, ["--help"])
        
        assert result.exit_code == 0
        assert "check-resources" in result.output
        assert "check-port" in result.output
        assert "check-http" in result.output
        assert "logs" in result.output
        assert "watch" in result.output
