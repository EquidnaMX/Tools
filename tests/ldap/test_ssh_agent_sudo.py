"""Regression coverage for both independent sudo PAM services."""

import subprocess
import os
import sys

import pytest
from click.testing import CliRunner

from tools.cli.ldap_commands import ldap
from tools.ldap import InstallationMode, LDAPClientInstaller, LDAPConfig
from tools.ldap.ssh_agent_sudo import configure_services


@pytest.fixture
def public_key(tmp_path):
    key = tmp_path / "identity"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    return key.with_suffix(".pub")


@pytest.mark.parametrize("mode", list(InstallationMode))
def test_installer_backs_up_both_sudo_services_and_installs_only_public_key(public_key, mode):
    plan = LDAPClientInstaller(
        LDAPConfig("ldap://ldap.example.test", "dc=example,dc=test"),
        mode=mode,
        ssh_sudo_user="gruelas",
        ssh_sudo_public_key=str(public_key),
    )
    script = plan.generate_script()
    assert "libpam-ssh-agent-auth" in script
    assert public_key.read_text().strip() in script
    assert "PRIVATE KEY" not in script
    assert "NOPASSWD" not in script
    assert 'Defaults:gruelas env_keep += "SSH_AUTH_SOCK"' in script
    for service in ("sudo", "sudo-i"):
        assert f"backup_file /etc/pam.d/{service} " in script
    assert script.index("backup_file /etc/pam.d/sudo-i ") < script.index("apt-get install")
    assert script.index("visudo -cf") < script.index("configure_services(")
    assert "/etc/security/authorized_keys_sudo_gruelas" in script
    assert "chmod 600" in script


def test_cli_generates_agent_configuration_for_both_services(public_key, tmp_path):
    target = tmp_path / "install.sh"
    result = CliRunner().invoke(ldap, [
        "configure-client", "--ldap-uri", "ldap://ldap.example.test",
        "--base-dn", "dc=example,dc=test", "--ssh-sudo-user", "gruelas",
        "--ssh-sudo-public-key", str(public_key), "--output-script", str(target),
    ])
    assert result.exit_code == 0, result.output
    assert "backup_file /etc/pam.d/sudo-i " in target.read_text()


def test_agent_setup_is_opt_in():
    script = LDAPClientInstaller(LDAPConfig("ldap://ldap.example.test", "dc=test")).generate_script()
    assert "pam_ssh_agent_auth" not in script
    assert "/etc/pam.d/sudo" not in script


@pytest.mark.parametrize("options", [
    {"ssh_sudo_user": "gruelas"},
    {"ssh_sudo_public_key": "missing.pub"},
    {"ssh_sudo_user": "bad\nuser", "ssh_sudo_public_key": "missing.pub"},
])
def test_incomplete_or_unsafe_agent_options_rejected(options):
    with pytest.raises(ValueError):
        LDAPClientInstaller(LDAPConfig("ldap://ldap.example.test", "dc=test"), **options).generate_script()


def test_private_key_is_rejected(public_key):
    with pytest.raises(ValueError, match="public key"):
        LDAPClientInstaller(
            LDAPConfig("ldap://ldap.example.test", "dc=test"),
            ssh_sudo_user="gruelas", ssh_sudo_public_key=str(public_key.with_suffix("")),
        ).generate_script()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires POSIX file metadata")
@pytest.mark.parametrize("already_configured", [None, "sudo", "sudo-i"])
def test_both_services_authenticate_before_password_stack_and_preserve_checks(tmp_path, already_configured):
    key_path = "/etc/security/authorized_keys_sudo_gruelas"
    rule = f"auth sufficient pam_ssh_agent_auth.so file={key_path}"
    originals = {}
    for name in ("sudo", "sudo-i"):
        text = ("#%PAM-1.0\n@include common-auth\n@include common-account\n"
                "session required pam_limits.so\n@include common-session\n")
        originals[name] = text
        if name == already_configured:
            text += rule + "\n"  # Existing rule after password auth must be moved.
        (tmp_path / name).write_text(text)
        (tmp_path / name).chmod(0o640)
    configure_services(tmp_path, key_path)
    first = {name: (tmp_path / name).read_bytes() for name in originals}
    for name, original in originals.items():
        path = tmp_path / name
        content = path.read_text()
        assert content.count(rule) == 1
        assert content.index(rule) < content.index("@include common-auth")
        assert content.replace(rule + "\n", "") == original
        assert path.stat().st_mode & 0o777 == 0o640
        assert path.stat().st_uid == os.getuid()
    configure_services(tmp_path, key_path)
    assert first == {name: (tmp_path / name).read_bytes() for name in originals}


@pytest.mark.parametrize("problem", ["missing", "conflict", "symlink"])
def test_invalid_second_service_never_changes_first(tmp_path, problem):
    original = "#%PAM-1.0\n@include common-auth\n@include common-account\n"
    (tmp_path / "sudo").write_text(original)
    if problem == "conflict":
        (tmp_path / "sudo-i").write_text("auth sufficient pam_ssh_agent_auth.so file=/other/key\n")
    elif problem == "symlink":
        target = tmp_path / "outside"
        target.write_text(original)
        try:
            (tmp_path / "sudo-i").symlink_to(target)
        except OSError:
            pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError):
        configure_services(tmp_path, "/etc/security/authorized_keys_sudo_gruelas")
    assert (tmp_path / "sudo").read_text() == original


def test_preview_reports_both_services_without_modifying_files(public_key, capsys):
    plan = LDAPClientInstaller(
        LDAPConfig("ldap://ldap.example.test", "dc=test"), dry_run=True,
        ssh_sudo_user="gruelas", ssh_sudo_public_key=str(public_key),
    )
    assert plan.install().success
    output = capsys.readouterr().out
    assert "/etc/pam.d/sudo and /etc/pam.d/sudo-i" in output
    assert not plan.backups_created


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires bash")
def test_generated_script_parses_and_preflights_visudo_before_rollback(public_key):
    script = LDAPClientInstaller(
        LDAPConfig("ldap://ldap.example.test", "dc=test"),
        ssh_sudo_user="gruelas", ssh_sudo_public_key=str(public_key),
    ).generate_script()
    result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert script.index("visudo -c\n") < script.index("trap 'rollback' ERR")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires bash and POSIX metadata")
def test_script_rollback_restores_both_services_after_partial_write(public_key, tmp_path):
    import shlex

    script = LDAPClientInstaller(
        LDAPConfig("ldap://ldap.example.test", "dc=test"),
        ssh_sudo_user="gruelas", ssh_sudo_public_key=str(public_key),
    ).generate_script()
    functions = script[script.index("backup_file() {"):script.index("trap 'rollback' ERR")]
    pam_dir = tmp_path / "pam.d"
    pam_dir.mkdir()
    backup = tmp_path / "backups"
    backup.mkdir()
    (backup / "manifest").touch()
    (backup / "active-services").touch()
    original = "#%PAM-1.0\n@include common-auth\n@include common-account\n"
    for service in ("sudo", "sudo-i"):
        (pam_dir / service).write_text(original)
        (pam_dir / service).chmod(0o640)
    commands = tmp_path / "bin"
    commands.mkdir()
    systemctl = commands / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 0\n")
    systemctl.chmod(0o755)
    # Execute the actual emitted helper, then emulate a write failure in sudo-i.
    helper = script.split("<<'TOOLS_SUDO_PAM_EOF'\n", 1)[1].split("\nTOOLS_SUDO_PAM_EOF", 1)[0]
    helper = helper.split('if __name__ == "__main__":', 1)[0]
    helper += '''
real_replace = os.replace
def fail_second(source, target):
    if Path(target).name == "sudo-i":
        raise OSError("simulated sudo-i write failure")
    real_replace(source, target)
os.replace = fail_second
configure_services(PAM_DIR, "/etc/security/authorized_keys_sudo_gruelas")
'''
    program = (
        "set -Eeuo pipefail\nbackup_dir=" + shlex.quote(str(backup))
        + '\nstaged=""\n' + functions + "trap 'rollback' ERR\n"
        + "backup_file " + shlex.quote(str(pam_dir / "sudo")) + " 0\n"
        + "backup_file " + shlex.quote(str(pam_dir / "sudo-i")) + " 1\n"
        + shlex.quote(sys.executable) + " - <<'TEST_HELPER_EOF'\nPAM_DIR="
        + repr(str(pam_dir)) + "\n" + helper + "\nTEST_HELPER_EOF\n"
    )
    result = subprocess.run(
        ["bash"], input=program, text=True, capture_output=True,
        env=dict(os.environ, PATH=str(commands) + ":" + os.environ["PATH"]),
    )
    assert result.returncode != 0
    assert "simulated sudo-i write failure" in result.stderr
    for service in ("sudo", "sudo-i"):
        assert (pam_dir / service).read_text() == original
        assert (pam_dir / service).stat().st_mode & 0o777 == 0o640
    assert not list(pam_dir.glob(".tools-agent-*"))
