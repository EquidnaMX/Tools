"""
Tests para LDAPClientInstaller.
"""

from tools.ldap import (
    LDAPClientInstaller,
    LDAPConfig,
    PAMConfig,
    InstallationMode,
)


class TestLDAPClientInstaller:
    """Tests para LDAPClientInstaller."""

    def test_create_installer_nslcd(self):
        """Test crear instalador con modo NSLCD."""
        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            mode=InstallationMode.NSLCD,
            dry_run=True,
        )

        assert installer.mode == InstallationMode.NSLCD
        assert installer.ldap_config.uri == "ldap://ldap.example.com"
        assert installer.dry_run is True

    def test_create_installer_sssd(self):
        """Test crear instalador con modo SSSD."""
        ldap_config = LDAPConfig(
            uri="ldaps://ldap.example.com",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret123",
        )

        pam_config = PAMConfig(
            allowed_groups=["admins", "users"],
            create_home_dir=True,
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            pam_config=pam_config,
            mode=InstallationMode.SSSD,
            dry_run=True,
        )

        assert installer.mode == InstallationMode.SSSD
        assert installer.pam_config.allowed_groups == ["admins", "users"]

    def test_generate_pam_configs(self):
        """Test generación de configuraciones PAM."""
        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        pam_config = PAMConfig(
            allowed_groups=["server-admin"],
            password_hash="yescrypt",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            pam_config=pam_config,
            dry_run=True,
        )

        configs = installer._generate_pam_configs()

        assert "common-auth" in configs
        assert "common-account" in configs
        assert "common-password" in configs
        assert "common-session" in configs
        assert "su" in configs

        # Verificar contenido
        assert "pam_unix.so" in configs["common-auth"]
        assert "pam_ldap.so" in configs["common-auth"]
        assert "server-admin" in configs["common-auth"]
        assert "yescrypt" in configs["common-password"]

    def test_installation_dry_run(self):
        """Test instalación en modo dry-run."""
        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            mode=InstallationMode.NSLCD,
            dry_run=True,
        )

        result = installer.install()

        assert result is not None
        assert result.mode == InstallationMode.NSLCD
        assert len(result.steps_completed) > 0

    def test_generate_script(self):
        """Test generación de script bash."""
        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            mode=InstallationMode.NSLCD,
            dry_run=True,
        )

        script = installer.generate_script()

        assert "#!/bin/bash" in script
        assert "ldap.example.com" in script
        assert "dc=example,dc=com" in script
        assert "libpam-ldapd" in script
        assert "backup_file" in script

    def test_pam_config_defaults(self):
        """Test valores por defecto de PAMConfig."""
        pam_config = PAMConfig()

        assert "server-admin" in pam_config.allowed_groups
        assert "desarrollo" in pam_config.allowed_groups
        assert pam_config.create_home_dir is True
        assert pam_config.password_hash == "yescrypt"

    def test_ldap_config_with_tls(self):
        """Test configuración LDAP con TLS."""
        ldap_config = LDAPConfig(
            uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            use_tls=True,
            tls_reqcert="demand",
        )

        assert ldap_config.use_tls is True
        assert ldap_config.tls_reqcert == "demand"
        assert "ldaps://" in ldap_config.uri

    def test_installation_mode_enum(self):
        """Test enumeración de modos de instalación."""
        assert InstallationMode.NSLCD.value == "nslcd"
        assert InstallationMode.SSSD.value == "sssd"

    def test_backup_creation(self):
        """Test creación de backups."""
        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            dry_run=True,
        )

        # Simular backup
        success = installer._backup_configuration_files()

        assert success is True
        assert len(installer.backups_created) > 0
        assert any("common-auth" in b for b in installer.backups_created)

    def test_multiple_allowed_groups(self):
        """Test con múltiples grupos permitidos."""
        pam_config = PAMConfig(
            allowed_groups=["admins", "developers", "operators", "readonly"],
        )

        ldap_config = LDAPConfig(
            uri="ldap://ldap.example.com",
            base_dn="dc=example,dc=com",
        )

        installer = LDAPClientInstaller(
            ldap_config=ldap_config,
            pam_config=pam_config,
            dry_run=True,
        )

        configs = installer._generate_pam_configs()
        auth_config = configs["common-auth"]

        assert "admins" in auth_config
        assert "developers" in auth_config
        assert "operators" in auth_config
        assert "readonly" in auth_config

    def test_list_allowed_groups_from_common_auth(self, tmp_path):
        """Test listar grupos desde archivo common-auth."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup admins",
                    "auth    sufficient      pam_succeed_if.so user ingroup desarrollo",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        installer = LDAPClientInstaller(
            ldap_config=LDAPConfig(uri="ldap://ldap.example.com", base_dn="dc=example,dc=com"),
            dry_run=False,
        )

        groups = installer.list_allowed_groups(pam_auth_file=str(common_auth))
        assert groups == ["admins", "desarrollo"]

    def test_add_allowed_group_updates_file(self, tmp_path):
        """Test agregar grupo en common-auth."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup admins",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        installer = LDAPClientInstaller(
            ldap_config=LDAPConfig(uri="ldap://ldap.example.com", base_dn="dc=example,dc=com"),
            dry_run=False,
        )

        ok, _ = installer.add_allowed_group("desarrollo", pam_auth_file=str(common_auth))
        assert ok is True

        content = common_auth.read_text(encoding="utf-8")
        assert "ingroup admins" in content
        assert "ingroup desarrollo" in content

    def test_add_group_normalizes_block_and_order(self, tmp_path):
        """Test que add normaliza bloque y ordena grupos."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup zeta",
                    "auth    sufficient      pam_succeed_if.so user ingroup alpha",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        installer = LDAPClientInstaller(
            ldap_config=LDAPConfig(uri="ldap://ldap.example.com", base_dn="dc=example,dc=com"),
            dry_run=False,
        )

        ok, _ = installer.add_allowed_group("beta", pam_auth_file=str(common_auth))
        assert ok is True

        content = common_auth.read_text(encoding="utf-8")
        assert installer.GROUP_BLOCK_START in content
        assert installer.GROUP_BLOCK_END in content

        alpha_pos = content.find("ingroup alpha")
        beta_pos = content.find("ingroup beta")
        zeta_pos = content.find("ingroup zeta")
        assert alpha_pos < beta_pos < zeta_pos

    def test_remove_allowed_group_updates_file(self, tmp_path):
        """Test quitar grupo en common-auth."""
        common_auth = tmp_path / "common-auth"
        common_auth.write_text(
            "\n".join(
                [
                    "auth    sufficient      pam_unix.so",
                    "auth    sufficient      pam_succeed_if.so user ingroup admins",
                    "auth    sufficient      pam_succeed_if.so user ingroup desarrollo",
                    "auth    requisite       pam_deny.so",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        installer = LDAPClientInstaller(
            ldap_config=LDAPConfig(uri="ldap://ldap.example.com", base_dn="dc=example,dc=com"),
            dry_run=False,
        )

        ok, _ = installer.remove_allowed_group("admins", pam_auth_file=str(common_auth))
        assert ok is True

        content = common_auth.read_text(encoding="utf-8")
        assert "ingroup admins" not in content
        assert "ingroup desarrollo" in content
