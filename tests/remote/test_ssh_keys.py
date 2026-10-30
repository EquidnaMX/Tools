"""Exercise real key parsing and disposable authorized_keys files, without SSH."""

import json
import os
import stat
import subprocess

import pytest
from click.testing import CliRunner

from tools.cli.ssh_key_commands import keys
from tools.remote.ssh_keys import REMOTE_HELPER, inspect_server, load_servers, validate_public_key


@pytest.fixture
def public(tmp_path):
    private = tmp_path / "identity"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)], check=True)
    return private.with_suffix(".pub")


@pytest.fixture
def manage():
    if os.name != "posix":
        pytest.skip("Remote Linux helper needs POSIX flock and permissions")
    namespace = {}
    exec(REMOTE_HELPER, namespace)
    return namespace["manage"]


def test_key_validation(public, tmp_path):
    key = validate_public_key(public)
    assert key.fingerprint.startswith("SHA256:")
    result = subprocess.run(["ssh-keygen", "-l", "-E", "sha256", "-f", str(public)],
                            capture_output=True, text=True, check=True)
    assert key.fingerprint in result.stdout
    assert CliRunner().invoke(keys, ["validate", str(public)]).exit_code == 0
    for invalid in [public.with_suffix(""), tmp_path / "bad"]:
        if invalid.name == "bad":
            invalid.write_text("ssh-ed25519 AAAA forged")
        with pytest.raises(ValueError):
            validate_public_key(invalid)


def test_additive_idempotent_and_preserve_options(public, tmp_path, manage):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    key = validate_public_key(public).line
    assert manage(home, [key])["missing"] == 1
    assert not (home / ".ssh").exists()
    report = manage(home, [key], True)
    target = home / ".ssh/authorized_keys"
    assert report["changed"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    # An existing restricted key must never become an unrestricted duplicate.
    original = '# keep\ncommand="echo restricted",no-pty ' + key + "\n"
    target.write_text(original)
    assert not manage(home, [key], True)["changed"]
    assert target.read_text() == original


def test_backup_and_preserve_bytes(public, tmp_path, manage):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    directory = home / ".ssh"
    directory.mkdir(mode=0o700)
    target = directory / "authorized_keys"
    target.write_bytes(b"# existing without newline")
    key = validate_public_key(public).line
    report = manage(home, [key], True)
    assert target.read_text() == "# existing without newline\n" + key + "\n"
    from pathlib import Path
    assert Path(report["backup"]).read_bytes() == b"# existing without newline"


def test_reject_unsafe_target_and_permissions(public, tmp_path, manage):
    key = validate_public_key(public).line
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    directory = home / ".ssh"
    directory.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    target = directory / "authorized_keys"
    target.symlink_to(outside)
    with pytest.raises(ValueError):
        manage(home, [key], True)
    assert outside.read_text() == "unchanged"
    target.unlink()
    directory.chmod(0o777)
    with pytest.raises(ValueError):
        manage(home, [key], True)


@pytest.mark.parametrize("server", [
    {"host": "-oProxyCommand=bad", "user": "user"},
    {"host": "host", "user": "root;id"},
    {"host": "host", "user": "user", "port": True},
    {"host": "host", "user": "user", "port": 70000},
    {"host": "host", "user": "user", "sudo": True},
])
def test_invalid_inventory(tmp_path, server):
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps({"keys": {}, "servers": [dict(server, keys=[])]}))
    with pytest.raises(ValueError):
        load_servers(path)


def test_transport_is_explicit_strict_and_noninteractive(public, monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '{"missing":0,"changed":false}', "")

    key = validate_public_key(public)
    monkeypatch.setattr(subprocess, "run", run)
    assert inspect_server({"host": "host", "user": "user", "port": 2222}, [key])["success"]
    assert "StrictHostKeyChecking=yes" in commands[0]
    assert "BatchMode=yes" in commands[0]
    assert commands[0][-2] == "host"


def test_failed_host_does_not_hide_other_hosts(public, tmp_path, monkeypatch):
    inventory = tmp_path / "hosts.json"
    inventory.write_text(json.dumps({"keys": {"admin": str(public)}, "servers": [
        {"host": "one", "user": "u", "keys": ["admin"]},
        {"host": "two", "user": "u", "keys": ["admin"]},
    ]}))
    calls = []

    def inspect(server, *args, **kwargs):
        calls.append((server["host"], kwargs["apply"]))
        return dict(server, success=server["host"] != "one", missing=1)

    monkeypatch.setattr("tools.cli.ssh_key_commands.inspect_server", inspect)
    result = CliRunner().invoke(keys, ["sync", "--hosts-file", str(inventory)])
    assert result.exit_code != 0
    assert calls == [("one", False), ("two", False)]


def test_authoritative_revocation_and_empty_guard(public, tmp_path, manage):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    key = validate_public_key(public).line
    manage(home, [key], True)
    target = home / ".ssh/authorized_keys"
    previous = target.read_bytes()
    assert manage(home, [])["extra"] == 1
    with pytest.raises(ValueError, match="allow-empty"):
        manage(home, [], True)
    assert target.read_bytes() == previous
    report = manage(home, [], True, allow_empty=True)
    assert report["changed"] and report["extra"] == 1
    assert key not in target.read_text()
    assert not manage(home, [], True, allow_empty=True)["changed"]


def test_revoke_one_and_add_another(public, tmp_path, manage):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    old = validate_public_key(public).line
    manage(home, [old], True)
    second = tmp_path / "second"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(second)], check=True)
    new = validate_public_key(second.with_suffix(".pub")).line
    report = manage(home, [new], True)
    assert report["missing"] == 1 and report["extra"] == 1
    assert (home / ".ssh/authorized_keys").read_text() == new + "\n"


def test_failed_replace_keeps_previous_file(public, tmp_path, manage, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    key = validate_public_key(public).line
    manage(home, [key], True)
    target = home / ".ssh/authorized_keys"
    original = target.read_bytes()

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        manage(home, [], True, allow_empty=True)
    assert target.read_bytes() == original
    assert not list(target.parent.glob(".tools-keys-*"))


def test_different_account_key_sets_and_duplicate_rejection(public, tmp_path):
    inventory = {"keys": {"admin": public.name}, "servers": [
        {"host": "one", "user": "u", "keys": ["admin"]},
        {"host": "two", "user": "u", "keys": []},
    ]}
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory))
    servers = load_servers(path)
    assert len(servers[0]["keys"]) == 1 and servers[1]["keys"] == []
    inventory["servers"].append(inventory["servers"][0])
    path.write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="Duplicate"):
        load_servers(path)


def test_actual_remote_payload_in_disposable_home(public, tmp_path, monkeypatch):
    if os.name != "posix":
        pytest.skip("Remote helper requires Linux")
    home = tmp_path / "remote-home"
    home.mkdir(mode=0o700)
    key = validate_public_key(public)
    real_run = subprocess.run

    def run(command, **kwargs):
        # Replace only the SSH network boundary; execute the actual transmitted helper.
        return real_run(["bash", "-c", command[-1]], env=dict(os.environ, HOME=str(home)), **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    server = {"host": "example.test", "user": "admin", "port": 22}
    plan = inspect_server(server, [key])
    assert plan["success"] and plan["missing"] == 1
    assert not (home / ".ssh").exists()
    applied = inspect_server(server, [key], apply=True)
    assert applied["success"] and applied["changed"]
    verified = inspect_server(server, [key])
    assert verified["success"] and verified["missing"] == verified["extra"] == 0
    revoked = inspect_server(server, [], apply=True, allow_empty=True)
    assert revoked["success"] and revoked["revoked_fingerprints"] == [key.fingerprint]


def test_cli_apply_and_empty_flags(public, tmp_path, monkeypatch):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"keys": {}, "servers": [{"host": "host", "user": "u", "keys": []}]}))
    calls = []

    def inspect(server, desired, *args, **kwargs):
        calls.append(kwargs)
        return dict(server, success=True, missing=0, extra=0)

    monkeypatch.setattr("tools.cli.ssh_key_commands.inspect_server", inspect)
    result = CliRunner().invoke(keys, ["sync", "--hosts-file", str(path), "--apply", "--allow-empty"])
    assert result.exit_code == 0, result.output
    assert calls[0]["apply"] and calls[0]["allow_empty"]
