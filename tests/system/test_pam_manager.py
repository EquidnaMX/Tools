"""Tests for PAMManager."""

from pathlib import Path

import pytest

from tools.system.pam_manager import PAMManager, PAMManagerError

PamEnv = dict[str, Path]


@pytest.fixture
def pam_env(tmp_path: Path) -> PamEnv:
    pam_dir = tmp_path / "pam.d"
    pam_dir.mkdir()

    login = pam_dir / "login"
    login.write_text(
        "auth required pam_env.so\n"
        "auth required pam_unix.so\n"
        "account required pam_unix.so\n",
        encoding="utf-8",
    )

    sshd = pam_dir / "sshd"
    sshd.write_text(
        "auth required pam_sepermit.so\n"
        "auth include password-auth\n",
        encoding="utf-8",
    )

    return {
        "pam_dir": pam_dir,
        "login": login,
        "sshd": sshd,
    }


class TestPAMManager:
    def test_list_services(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        services = manager.list_services()

        names = [s.service for s in services]
        assert "login" in names
        assert "sshd" in names

    def test_read_service_ok(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        content = manager.read_service("login")

        assert "pam_unix.so" in content

    def test_read_service_not_found(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        with pytest.raises(PAMManagerError, match="not found"):
            manager.read_service("system-auth")

    def test_check_module_enabled_true(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        assert manager.check_module_enabled("login", "pam_unix.so") is True

    def test_check_module_enabled_false(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        assert manager.check_module_enabled("sshd", "pam_faillock.so") is False

    def test_create_backup(self, pam_env: PamEnv, tmp_path: Path):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        backup_dir = tmp_path / "backups"

        backup_path = manager.create_backup("login", backup_dir)

        assert backup_path.exists()
        assert backup_path.name.startswith("login.")
        assert backup_path.read_text(encoding="utf-8") == pam_env["login"].read_text(encoding="utf-8")

    def test_restore_backup(self, pam_env: PamEnv, tmp_path: Path):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        backup_file = tmp_path / "login.bak"
        backup_file.write_text("auth required pam_securetty.so\n", encoding="utf-8")

        ok = manager.restore_backup("login", backup_file)

        assert ok is True
        assert pam_env["login"].read_text(encoding="utf-8") == "auth required pam_securetty.so\n"

    def test_restore_backup_dry_run(self, pam_env: PamEnv, tmp_path: Path):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        backup_file = tmp_path / "login.bak"
        backup_file.write_text("auth required pam_securetty.so\n", encoding="utf-8")

        ok = manager.restore_backup("login", backup_file, dry_run=True)

        assert ok is True
        assert "pam_unix.so" in pam_env["login"].read_text(encoding="utf-8")

    def test_ensure_line_replaces_by_pattern(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.ensure_line(
            service="login",
            line="auth required pam_faillock.so preauth silent",
            match_pattern=r"pam_unix\.so",
        )

        assert result.updated is True
        content = pam_env["login"].read_text(encoding="utf-8")
        assert "pam_faillock.so" in content

    def test_ensure_line_with_diff(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.ensure_line(
            service="login",
            line="session required pam_limits.so",
            show_diff=True,
        )

        assert result.updated is True
        assert result.diff is not None
        assert "session required pam_limits.so" in result.diff
        assert "---" in result.diff  # unified diff header
        assert "+++" in result.diff  # unified diff header

    def test_ensure_line_no_diff_when_no_changes(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        # Add a line first
        manager.ensure_line(service="login", line="session required pam_limits.so")

        # Try to add the same line again with diff enabled
        result = manager.ensure_line(
            service="login",
            line="session required pam_limits.so",
            show_diff=True,
        )

        assert result.updated is False
        assert result.diff is None

    def test_apply_hardening_sshd(self, pam_env: PamEnv, tmp_path: Path):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        backup_dir = tmp_path / "backups"

        result = manager.apply_hardening(
            service="sshd",
            backup_dir=backup_dir,
        )

        assert result.applied is True
        assert result.profile == "sshd"
        assert result.backup_path is not None
        assert result.backup_path.exists()

        # Check content was replaced with hardening profile
        content = pam_env["sshd"].read_text(encoding="utf-8")
        assert "pam_faillock.so" in content
        assert "pam_pwquality.so" in content

    def test_apply_hardening_with_custom_profile(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.apply_hardening(
            service="sshd",
            profile="login",  # Use login profile for sshd service
        )

        assert result.applied is True
        assert result.profile == "login"

        content = pam_env["sshd"].read_text(encoding="utf-8")
        assert "pam_securetty.so" in content  # login profile includes this

    def test_apply_hardening_dry_run(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])
        original_content = pam_env["sshd"].read_text(encoding="utf-8")

        result = manager.apply_hardening(
            service="sshd",
            dry_run=True,
        )

        assert result.applied is True
        assert result.dry_run is True
        # Content should not change in dry-run
        assert pam_env["sshd"].read_text(encoding="utf-8") == original_content

    def test_apply_hardening_with_diff(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.apply_hardening(
            service="sshd",
            show_diff=True,
        )

        assert result.applied is True
        assert result.diff is not None
        assert "pam_faillock.so" in result.diff
        assert "---" in result.diff
        assert "+++" in result.diff

    def test_apply_hardening_already_applied(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        # Apply hardening first time
        manager.apply_hardening(service="sshd")

        # Try to apply again
        result = manager.apply_hardening(service="sshd")

        assert result.applied is False

    def test_apply_hardening_unknown_profile(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        with pytest.raises(PAMManagerError, match="Unknown hardening profile"):
            manager.apply_hardening(service="sshd", profile="nonexistent")

    def test_hardening_profiles_exist(self):
        from tools.system.pam_manager import HARDENING_PROFILES

        # Check that expected profiles exist
        assert "sshd" in HARDENING_PROFILES
        assert "login" in HARDENING_PROFILES
        assert "su" in HARDENING_PROFILES

        # Check profiles have content
        for lines in HARDENING_PROFILES.values():
            assert isinstance(lines, list)
            assert len(lines) > 0

    def test_ensure_line_inserts_after_pattern(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.ensure_line(
            service="sshd",
            line="account required pam_access.so",
            after_pattern=r"auth include password-auth",
        )

        assert result.updated is True
        content = pam_env["sshd"].read_text(encoding="utf-8")
        assert "account required pam_access.so" in content

    def test_ensure_line_no_change(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.ensure_line(
            service="login",
            line="auth required pam_env.so",
        )

        assert result.updated is False

    def test_ensure_line_with_backup_dir(self, pam_env: PamEnv, tmp_path: Path):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        result = manager.ensure_line(
            service="sshd",
            line="session required pam_lastlog.so",
            backup_dir=tmp_path / "pam_backups",
        )

        assert result.updated is True
        assert result.backup_path is not None
        assert result.backup_path.exists()

    def test_invalid_service_name(self, pam_env: PamEnv):
        manager = PAMManager(pam_dir=pam_env["pam_dir"])

        with pytest.raises(PAMManagerError, match="Invalid PAM service"):
            manager.read_service("../../passwd")
