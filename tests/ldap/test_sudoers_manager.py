"""Tests para gestión de sudoers LDAP helper."""

import pytest

from tools.ldap import SudoersManager, SudoersRule


class TestSudoersManager:
    """Tests para SudoersManager."""

    @pytest.fixture(autouse=True)
    def valid_parser(self, monkeypatch):
        # Filesystem unit cases; real parser and rejection cases live in test_sudoers_safety.
        monkeypatch.setattr(
            SudoersManager, "_validate_file", staticmethod(lambda *args: (True, "OK"))
        )

    def test_sudoers_rule_format(self):
        rule = SudoersRule(
            group="hela-admin",
            run_as="root:www-data",
            commands="ALL, !/usr/bin/passwd",
        )

        assert rule.to_line() == "%hela-admin ALL=(root:www-data) ALL, !/usr/bin/passwd"

    def test_create_rule_file(self, tmp_path):
        manager = SudoersManager(dry_run=False)
        rule = SudoersRule(group="hela-admin", run_as="root", commands="ALL")

        ok, message = manager.create_rule_file(
            file_name="hela-admin",
            rule=rule,
            sudoers_dir=str(tmp_path),
            validate=False,
        )

        assert ok is True
        assert "Archivo creado" in message

        content = (tmp_path / "hela-admin").read_text(encoding="utf-8")
        assert "%hela-admin ALL=(root) ALL" in content

    def test_list_rule_files(self, tmp_path):
        (tmp_path / "a-rule").write_text("# a\n", encoding="utf-8")
        (tmp_path / "b-rule").write_text("# b\n", encoding="utf-8")

        manager = SudoersManager(dry_run=False)
        files = manager.list_rule_files(sudoers_dir=str(tmp_path))

        assert files == ["a-rule", "b-rule"]

    def test_show_rule_file(self, tmp_path):
        file_path = tmp_path / "hela-admin"
        file_path.write_text("%hela-admin ALL=(root) ALL\n", encoding="utf-8")

        manager = SudoersManager(dry_run=False)
        ok, content = manager.show_rule_file("hela-admin", sudoers_dir=str(tmp_path))

        assert ok is True
        assert "%hela-admin ALL=(root) ALL" in content

    def test_remove_rule_file(self, tmp_path):
        file_path = tmp_path / "hela-admin"
        file_path.write_text("%hela-admin ALL=(root) ALL\n", encoding="utf-8")

        manager = SudoersManager(dry_run=False)
        ok, _ = manager.remove_rule_file("hela-admin", sudoers_dir=str(tmp_path))

        assert ok is True
        assert not file_path.exists()

    def test_create_rule_file_dry_run(self, tmp_path):
        manager = SudoersManager(dry_run=True)
        rule = SudoersRule(group="hela-admin", run_as="root", commands="ALL")

        ok, message = manager.create_rule_file(
            file_name="hela-admin",
            rule=rule,
            sudoers_dir=str(tmp_path),
            validate=False,
        )

        assert ok is True
        assert "DRY-RUN" in message
        assert not (tmp_path / "hela-admin").exists()
