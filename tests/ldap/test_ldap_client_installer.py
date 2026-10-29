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
        assert "server-admin" in configs["common-account"]
        assert "server-admin" not in configs["common-auth"]
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

        result = installer.install()
        assert result.success is True
        assert result.backups_created == []
        assert "no files" in result.message

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
        auth_config = configs["common-account"]

        assert "admins" in auth_config
        assert "developers" in auth_config
        assert "operators" in auth_config
        assert "readonly" in auth_config

    def test_list_allowed_groups_from_account_policy(self, tmp_path):
        path = tmp_path / "common-account"
        path.write_text("account required pam_permit.so\n", encoding="utf-8")
        installer = LDAPClientInstaller(LDAPConfig("ldap://example.test", "dc=test"))
        assert installer.add_allowed_group("admins", pam_account_file=str(path))[0]
        assert installer.add_allowed_group("desarrollo", pam_account_file=str(path))[0]
        assert installer.list_allowed_groups(pam_account_file=str(path)) == [
            "admins",
            "desarrollo",
        ]

    def test_add_allowed_group_updates_file(self, tmp_path):
        path = tmp_path / "common-account"
        path.write_text("account required pam_unix.so\n", encoding="utf-8")
        installer = LDAPClientInstaller(LDAPConfig("ldap://example.test", "dc=test"))
        assert installer.add_allowed_group("admins", pam_account_file=str(path))[0]
        assert installer.add_allowed_group("desarrollo", pam_account_file=str(path))[0]
        assert "ingroup admins:desarrollo" in path.read_text()
        assert path.read_text().endswith("account required pam_unix.so\n")

    def test_add_group_normalizes_block_and_order(self, tmp_path):
        path = tmp_path / "common-account"
        path.write_text("account required pam_permit.so\n", encoding="utf-8")
        installer = LDAPClientInstaller(LDAPConfig("ldap://example.test", "dc=test"))
        for group in ["zeta", "alpha", "beta"]:
            assert installer.add_allowed_group(group, pam_account_file=str(path))[0]
        content = path.read_text()
        assert content.count(installer.GROUP_BLOCK_START) == 1
        assert "ingroup alpha:beta:zeta" in content

    def test_remove_allowed_group_updates_file(self, tmp_path):
        path = tmp_path / "common-account"
        path.write_text("account required pam_permit.so\n", encoding="utf-8")
        installer = LDAPClientInstaller(LDAPConfig("ldap://example.test", "dc=test"))
        for group in ["admins", "desarrollo"]:
            assert installer.add_allowed_group(group, pam_account_file=str(path))[0]
        assert installer.remove_allowed_group("admins", pam_account_file=str(path))[0]
        assert installer.list_allowed_groups(pam_account_file=str(path)) == [
            "desarrollo"
        ]
