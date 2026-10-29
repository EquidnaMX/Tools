"""Regression checks for LDAP plans and PAM authorization boundaries."""

import ctypes
import ctypes.util
import os
import subprocess
import sys

import pytest

from tools.ldap import LDAPClientInstaller, LDAPConfig, InstallationMode


def installer(**kwargs):
    return LDAPClientInstaller(
        LDAPConfig(uri="ldap://ldap.example.test", base_dn="dc=example,dc=test"),
        **kwargs,
    )


def test_direct_install_fails_without_side_effects(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("An unsupported installer must not modify the host")

    monkeypatch.setattr(subprocess, "run", unexpected)
    from pathlib import Path

    monkeypatch.setattr(Path, "write_text", unexpected)
    result = installer().install()
    assert not result.success
    assert not result.steps_completed
    assert not result.backups_created
    assert "script" in result.message.lower()


def test_remote_install_is_not_silently_applied_locally():
    result = installer(dry_run=True).install(remote_host="remote.example.test")
    assert not result.success
    assert not result.steps_completed


@pytest.mark.parametrize("password", ["private-test-value", 'private-"test\\value'])
def test_preview_records_no_real_backups_and_redacts_password(capsys, password):
    plan = installer(dry_run=True)
    plan.ldap_config.bind_dn = "cn=reader,dc=example,dc=test"
    plan.ldap_config.bind_password = password
    assert plan.install().success
    assert not plan.backups_created
    output = capsys.readouterr().out
    assert "private-" not in output
    assert "<REDACTED>" in output


def test_repeated_preview_does_not_accumulate_results(capsys):
    plan = installer(dry_run=True)
    first = plan.install()
    second = plan.install()
    assert first.steps_completed == second.steps_completed


@pytest.mark.parametrize("mode", list(InstallationMode))
def test_generated_script_keeps_tls_bind_and_backend(mode):
    plan = installer(mode=mode)
    plan.ldap_config.bind_dn = "cn=reader,dc=example,dc=test"
    plan.ldap_config.bind_password = "literal-$value-'\"-test"
    script = plan.generate_script()
    import shlex

    if mode == InstallationMode.NSLCD:
        bind_line = next(
            line for line in script.splitlines() if line.startswith("bindpw ")
        )
        assert shlex.split(bind_line)[1] == plan.ldap_config.bind_password
    else:
        assert plan.ldap_config.bind_password in script
    assert "/etc/ssl/certs/ca-certificates.crt" in script
    if mode == InstallationMode.NSLCD:
        assert "ssl start_tls" in script
        assert "tls_reqcert demand" in script
        assert "libnss-ldapd" in script
    else:
        assert "[domain/LDAP]" in script
        assert "ldap_id_use_start_tls = true" in script
        assert "pam_sss.so" in script
        assert "pam_ldap.so" not in script
        assert "files sss" in script
    assert "trap " in script
    if sys.platform.startswith("linux"):
        result = subprocess.run(
            ["bash", "-n"], input=script, text=True, capture_output=True
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("attribute", ["uri", "base_dn", "bind_password"])
def test_multiline_config_injection_rejected(attribute):
    plan = installer()
    setattr(plan.ldap_config, attribute, "value\nNSLCDEOF\ntouch /tmp/unwanted")
    with pytest.raises(ValueError):
        plan.generate_script()


def test_group_edit_refuses_auth_stack(tmp_path):
    auth = tmp_path / "common-auth"
    original = (
        "auth [success=1 default=ignore] pam_unix.so\nauth requisite pam_deny.so\n"
    )
    auth.write_text(original)
    ok, message = installer().add_allowed_group("admins", pam_auth_file=str(auth))
    assert not ok
    assert "account" in message
    assert auth.read_text() == original


def test_group_edit_preserves_existing_account_checks(tmp_path):
    account = tmp_path / "common-account"
    original = "account required pam_unix.so\naccount required pam_time.so\n"
    account.write_text(original)
    plan = installer()
    assert plan.add_allowed_group("admins", pam_account_file=str(account))[0]
    assert plan.add_allowed_group("operators", pam_account_file=str(account))[0]
    content = account.read_text()
    assert content.endswith(original)
    assert "auth " not in content
    assert plan.list_allowed_groups(pam_account_file=str(account)) == [
        "admins",
        "operators",
    ]
    assert plan.remove_allowed_group("admins", pam_account_file=str(account))[0]
    assert plan.list_allowed_groups(pam_account_file=str(account)) == ["operators"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires Linux PAM")
@pytest.mark.parametrize("valid_auth", [False, True])
@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("account_include", [False, True])
def test_real_pam_authentication_and_account_are_independent(
    tmp_path, valid_auth, allowed, account_include
):
    """Use real PAM dispatch and group lookup, with a simulated LDAP identity."""
    import grp
    import pwd

    library = ctypes.util.find_library("pam")
    if not library:
        pytest.skip("libpam unavailable")
    pam = ctypes.CDLL(library)
    if not hasattr(pam, "pam_start_confdir"):
        pytest.skip("pam_start_confdir unavailable")
    callback_type = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )
    callback = callback_type(lambda *args: 19)

    class Conversation(ctypes.Structure):
        _fields_ = [("conv", callback_type), ("data", ctypes.c_void_p)]

    pam.pam_start_confdir.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(Conversation),
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    pam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_acct_mgmt.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name if allowed else "tools_missing_group_6729"
    auth_module = "pam_permit.so" if valid_auth else "pam_deny.so"
    service = tmp_path / "review"
    auth = (
        f"auth [success=1 default=ignore] {auth_module}\n"
        "auth requisite pam_deny.so\nauth required pam_permit.so\n"
    )
    account = "account required pam_permit.so\n"
    if account_include:
        (tmp_path / "permissive-account").write_text(
            "account sufficient pam_permit.so\n"
        )
        account = "@include permissive-account\n"
    service.write_text(auth + account)
    assert installer().add_allowed_group(group, pam_account_file=str(service))[0]
    # The fixture emulates a non-local identity without contacting an LDAP server.
    content = service.read_text().replace("pam_localuser.so", "pam_deny.so")
    service.write_text(content)
    assert content.startswith(auth)
    handle = ctypes.c_void_p()
    conversation = Conversation(callback, None)
    assert (
        pam.pam_start_confdir(
            b"review",
            user.encode(),
            ctypes.byref(conversation),
            str(tmp_path).encode(),
            ctypes.byref(handle),
        )
        == 0
    )
    try:
        assert (pam.pam_authenticate(handle, 0) == 0) is valid_auth
        # Account-only calls also protect public-key SSH and agent-authenticated sudo.
        assert (pam.pam_acct_mgmt(handle, 0) == 0) is allowed
    finally:
        pam.pam_end(handle, 0)


def test_linux_script_paths_are_independent_of_generator_os(monkeypatch):
    from pathlib import PureWindowsPath

    monkeypatch.setattr("tools.ldap.client_installer.Path", PureWindowsPath)
    script = installer(mode=InstallationMode.SSSD).generate_script()
    assert "mkdir -p -- /etc/sssd" in script
    assert "\\etc\\" not in script


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires bash")
@pytest.mark.parametrize("previously_active", ["", "nslcd\n"])
def test_script_rollback_restores_service_activity(tmp_path, previously_active):
    import shlex

    script = installer().generate_script()
    function = (
        "rollback() {"
        + script.split("rollback() {", 1)[1].split("\n}\n", 1)[0]
        + "\n}\n"
    )
    backup = tmp_path / "backup"
    backup.mkdir()
    old_config = tmp_path / "old config"
    new_config = tmp_path / "new config"
    old_config.write_text("changed")
    new_config.write_text("new")
    (backup / "0").write_text("original")
    (backup / "manifest").write_text(f"yes\t0\t{old_config}\nno\t1\t{new_config}\n")
    (backup / "active-services").write_text(previously_active)
    commands = tmp_path / "bin"
    commands.mkdir()
    stub = commands / "systemctl"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n')
    stub.chmod(0o755)
    log = tmp_path / "calls"
    result = subprocess.run(
        ["bash"],
        input="set -euo pipefail\nbackup_dir="
        + shlex.quote(str(backup))
        + '\nstaged=""\n'
        + function
        + "rollback\n",
        text=True,
        capture_output=True,
        env=dict(
            os.environ, PATH=str(commands) + ":" + os.environ["PATH"], CALL_LOG=str(log)
        ),
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "restart nslcd" if previously_active else "stop nslcd",
        "stop nscd",
    ]
    assert old_config.read_text() == "original"
    assert not new_config.exists()


def test_remove_last_group_denies_nonlocal_accounts(tmp_path):
    account = tmp_path / "common-account"
    account.write_text("account required pam_permit.so\n")
    plan = installer()
    assert plan.add_allowed_group("admins", pam_account_file=str(account))[0]
    assert plan.remove_allowed_group("admins", pam_account_file=str(account))[0]
    assert plan.list_allowed_groups(pam_account_file=str(account)) == []
    assert "account requisite pam_deny.so" in account.read_text()


def test_misplaced_existing_gate_is_rejected_without_reordering(tmp_path):
    account = tmp_path / "common-account"
    plan = installer()
    content = "@include permissive\n" + "\n".join(plan._group_block(["admins"])) + "\n"
    account.write_text(content)
    ok, message = plan.add_allowed_group("operators", pam_account_file=str(account))
    assert not ok and "precede" in message
    assert account.read_text() == content
