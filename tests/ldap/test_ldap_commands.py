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
        assert "sudoers" in result.output

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

    def test_groups_list(self, tmp_path):
        """Test listar grupos LDAP de common-auth."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup server-admin",
                    "auth    sufficient      pam_succeed_if.so user ingroup desarrollo",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["groups", "list", "--pam-auth-file", str(common_auth)],
        )

        assert result.exit_code == 0
        assert "server-admin" in result.output
        assert "desarrollo" in result.output

    def test_groups_add(self, tmp_path):
        """Test agregar grupo LDAP por CLI."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup server-admin",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["groups", "add", "desarrollo", "--pam-auth-file", str(common_auth)],
        )

        assert result.exit_code == 0
        content = common_auth.read_text(encoding="utf-8")
        assert "ingroup desarrollo" in content

    def test_groups_remove(self, tmp_path):
        """Test quitar grupo LDAP por CLI."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup server-admin",
                    "auth    sufficient      pam_succeed_if.so user ingroup desarrollo",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["groups", "remove", "desarrollo", "--pam-auth-file", str(common_auth)],
        )

        assert result.exit_code == 0
        content = common_auth.read_text(encoding="utf-8")
        assert "ingroup desarrollo" not in content

    def test_sudoers_create(self, tmp_path):
        """Test crear regla sudoers por CLI."""
        runner = CliRunner()
        result = runner.invoke(
            ldap,
            [
                "sudoers",
                "create",
                "--name",
                "hela-admin",
                "--group",
                "hela-admin",
                "--run-as",
                "root:www-data",
                "--commands",
                "ALL, !/usr/bin/passwd",
                "--sudoers-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        content = (tmp_path / "hela-admin").read_text(encoding="utf-8")
        assert "%hela-admin ALL=(root:www-data) ALL, !/usr/bin/passwd" in content

    def test_sudoers_list(self, tmp_path):
        """Test listar reglas sudoers por CLI."""
        (tmp_path / "hela-admin").write_text("%hela-admin ALL=(root) ALL\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["sudoers", "list", "--sudoers-dir", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "hela-admin" in result.output

    def test_sudoers_remove(self, tmp_path):
        """Test eliminar regla sudoers por CLI."""
        (tmp_path / "hela-admin").write_text("%hela-admin ALL=(root) ALL\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            ldap,
            ["sudoers", "remove", "hela-admin", "--sudoers-dir", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert not (tmp_path / "hela-admin").exists()
