"""
Tests para comandos CLI de LDAP.
"""

from click.testing import CliRunner
from tools.cli.ldap_commands import ldap
import os


class TestLDAPCommands:
    """Tests para comandos CLI de LDAP."""

    def test_ldap_group(self):
        """Test que el grupo de comandos funciona."""
        runner = CliRunner()
        result = runner.invoke(ldap, ["--help"])

        assert result.exit_code == 0
        assert "configure-client" in result.output
        assert "test-connection" in result.output
        assert "generate-config" in result.output

    def test_configure_client_dry_run(self):
        """Test comando configure-client en modo dry-run."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        assert "test.example.com" in result.output

    def test_configure_client_with_groups(self):
        """Test configuración con grupos específicos."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "-g", "admins",
                "-g", "users",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "admins" in result.output
        assert "users" in result.output

    def test_configure_client_sssd_mode(self):
        """Test configuración con modo SSSD."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "--mode", "sssd",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "SSSD" in result.output

    def test_generate_script(self, tmp_path):
        """Test generación de script bash."""
        script_file = tmp_path / "test_ldap.sh"

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "--output-script", str(script_file),
            ],
        )

        assert result.exit_code == 0
        assert script_file.exists()

        # Verificar contenido del script
        content = script_file.read_text()
        assert "#!/bin/bash" in content
        assert "test.example.com" in content
        assert "dc=test,dc=com" in content

        # Verificar que tiene permisos de ejecución
        assert os.access(script_file, os.X_OK)

    def test_generate_config(self, tmp_path):
        """Test generación de archivo de configuración."""
        config_file = tmp_path / "test_config.yaml"

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["generate-config", "-o", str(config_file)],
        )

        assert result.exit_code == 0
        assert config_file.exists()

        # Verificar contenido
        content = config_file.read_text()
        assert "ldap:" in content
        assert "pam:" in content
        assert "uri:" in content
        assert "base_dn:" in content

    def test_configure_with_bind_credentials(self):
        """Test configuración con credenciales de bind."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldaps://secure.example.com",
                "--base-dn", "dc=example,dc=com",
                "--bind-dn", "cn=admin,dc=example,dc=com",
                "--bind-password", "secret123",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "secure.example.com" in result.output
        assert "cn=admin" in result.output

    def test_configure_no_tls(self):
        """Test configuración sin TLS."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "--no-tls",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

    def test_configure_custom_password_hash(self):
        """Test con algoritmo de hash personalizado."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "configure-client",
                "--ldap-uri", "ldap://test.example.com",
                "--base-dn", "dc=test,dc=com",
                "--password-hash", "sha512",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

    def test_missing_required_options(self):
        """Test fallo cuando faltan opciones requeridas."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["configure-client"],
        )

        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()
