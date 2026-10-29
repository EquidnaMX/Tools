"""Sudoers validation, containment and recovery regression checks."""

import os
import shutil
import subprocess

import pytest

from tools.ldap import SudoersManager, SudoersRule


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "..\\outside",
        "C:\\outside",
        "a/b",
        "a.conf",
        "a~",
        "",
        " rule",
    ],
)
def test_all_rule_operations_reject_unsafe_names(tmp_path, name):
    directory = tmp_path / "sudoers.d"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    manager = SudoersManager()
    assert not manager.create_rule_file(name, SudoersRule("admins"), str(directory))[0]
    assert not manager.show_rule_file(name, str(directory))[0]
    assert not manager.remove_rule_file(name, str(directory))[0]
    assert outside.read_text() == "unchanged"


def test_validation_cannot_be_disabled_and_failure_keeps_original(
    tmp_path, monkeypatch
):
    directory = tmp_path / "sudoers.d"
    directory.mkdir()
    target = directory / "admins"
    target.write_text("original")
    calls = []

    def reject(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "", "invalid rule")

    monkeypatch.setattr(subprocess, "run", reject)
    ok, _ = SudoersManager().create_rule_file(
        "admins", SudoersRule("admins"), str(directory), validate=False
    )
    assert not ok and len(calls) == 1
    assert target.read_text() == "original"
    assert list(directory.iterdir()) == [target]


def test_missing_visudo_never_installs_rule(tmp_path):
    ok, _ = SudoersManager().create_rule_file(
        "admins",
        SudoersRule("admins"),
        str(tmp_path),
        visudo_path=str(tmp_path / "missing"),
    )
    assert not ok
    assert not (tmp_path / "admins").exists()


def test_atomic_replacement_failure_keeps_original_and_backup(tmp_path, monkeypatch):
    directory = tmp_path / "sudoers.d"
    directory.mkdir()
    target = directory / "admins"
    target.write_text("original")
    monkeypatch.setattr(
        subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0)
    )

    def fail(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(os, "replace", fail)
    ok, _ = SudoersManager().create_rule_file(
        "admins", SudoersRule("admins"), str(directory)
    )
    assert not ok
    assert target.read_text() == "original"
    backups = list((tmp_path / "tools-sudoers-backups").iterdir())
    assert len(backups) == 1 and backups[0].read_text() == "original"
    assert list(directory.iterdir()) == [target]


def test_successful_replace_is_validated_and_recoverable(tmp_path, monkeypatch):
    directory = tmp_path / "sudoers.d"
    directory.mkdir()
    target = directory / "admins"
    target.write_text("original")
    monkeypatch.setattr(
        subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0)
    )
    manager = SudoersManager()
    assert manager.create_rule_file("admins", SudoersRule("admins"), str(directory))[0]
    assert "%admins ALL=(root) ALL" in target.read_text()
    assert (
        list((tmp_path / "tools-sudoers-backups").iterdir())[0].read_text()
        == "original"
    )
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o440


@pytest.mark.parametrize("field", ["group", "run_as", "commands"])
def test_newlines_cannot_add_another_sudoers_rule(tmp_path, field):
    fields = dict(group="admins", run_as="root", commands="ALL")
    fields[field] += "\nother ALL=(ALL) NOPASSWD: ALL"
    assert not SudoersManager().create_rule_file(
        "admins", SudoersRule(**fields), str(tmp_path)
    )[0]
    assert not (tmp_path / "admins").exists()


def test_symlink_rule_cannot_be_read_replaced_or_deleted(tmp_path):
    directory = tmp_path / "sudoers.d"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    try:
        (directory / "admins").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation not permitted")
    manager = SudoersManager()
    assert not manager.show_rule_file("admins", str(directory))[0]
    assert not manager.create_rule_file(
        "admins", SudoersRule("admins"), str(directory)
    )[0]
    assert not manager.remove_rule_file("admins", str(directory))[0]
    assert manager.list_rule_files(str(directory)) == []
    assert outside.read_text() == "unchanged"


@pytest.mark.skipif(
    not shutil.which("visudo"), reason="Requires installed visudo parser"
)
def test_real_visudo_accepts_valid_rule_and_rejects_invalid_rule(tmp_path):
    manager = SudoersManager()
    assert manager.create_rule_file("admins", SudoersRule("admins"), str(tmp_path))[0]
    original = (tmp_path / "admins").read_text()
    assert not manager.create_rule_file(
        "admins", SudoersRule("admins", commands="ALL ("), str(tmp_path)
    )[0]
    assert (tmp_path / "admins").read_text() == original


def test_run_as_cannot_inject_passwordless_tag(tmp_path):
    rule = SudoersRule("admins", run_as="root) NOPASSWD:ALL #")
    assert not SudoersManager().create_rule_file("admins", rule, str(tmp_path))[0]
    assert not (tmp_path / "admins").exists()
