"""Tests for DNS installer."""

from unittest.mock import MagicMock, patch

import pytest

from tools.dns.installer import DNSInstaller


class TestDNSInstaller:
    """DNSInstaller behavior tests."""

    @pytest.fixture
    def installer(self):
        return DNSInstaller(dry_run=False, timeout=30)

    @patch("subprocess.run")
    def test_run_shell_step_success(self, mock_run, installer):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")

        step = installer._run_shell_step("test", "echo ok")

        assert step.success is True
        assert step.output == "ok"

    @patch("subprocess.run")
    def test_run_shell_step_failure(self, mock_run, installer):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        step = installer._run_shell_step("test", "false")

        assert step.success is False
        assert step.error == "boom"

    def test_run_shell_step_dry_run(self):
        installer = DNSInstaller(dry_run=True)

        step = installer._run_shell_step("test", "echo ok")

        assert step.success is True
        assert step.output == "dry-run"

    @patch.object(DNSInstaller, "_run_shell_step")
    def test_execute_steps_stop_on_failure(self, mock_step, installer):
        ok = type("S", (), {"success": True})()
        fail = type("S", (), {"success": False})()
        mock_step.side_effect = [ok, fail, ok]

        report = installer._execute_steps("target", [("a", "x"), ("b", "y"), ("c", "z")])

        assert len(report.steps) == 2

    @patch.object(DNSInstaller, "_run_shell_step")
    def test_execute_steps_dry_run_does_not_stop(self, mock_step):
        installer = DNSInstaller(dry_run=True)
        ok = type("S", (), {"success": True})()
        mock_step.side_effect = [ok, ok, ok]

        report = installer._execute_steps("target", [("a", "x"), ("b", "y"), ("c", "z")])

        assert len(report.steps) == 3

    @patch.object(DNSInstaller, "_execute_steps")
    def test_install_bind9_slave(self, mock_exec, installer):
        mock_exec.return_value = type("R", (), {"target": "bind9-slave", "steps": []})()

        report = installer.install_bind9_slave(zone="example.com", master_ip="1.1.1.1")

        assert report.target == "bind9-slave"
        args = mock_exec.call_args[0]
        assert args[0] == "bind9-slave"
        assert len(args[1]) >= 6

    @patch.object(DNSInstaller, "_execute_steps")
    def test_install_pdns_master(self, mock_exec, installer):
        mock_exec.return_value = type("R", (), {"target": "pdns-master", "steps": []})()

        report = installer.install_pdns_master(
            slave_ip="2.2.2.2",
            db_root_password="rootpass",
            db_pdns_password="pdnspass",
            api_key="apikey",
        )

        assert report.target == "pdns-master"
        args = mock_exec.call_args[0]
        assert args[0] == "pdns-master"
        assert len(args[1]) >= 6

    def test_install_report_to_dict(self):
        installer = DNSInstaller(dry_run=True)
        report = installer._execute_steps("target", [("a", "x"), ("b", "y")])

        data = report.to_dict()

        assert data["target"] == "target"
        assert data["summary"]["total"] == 2
        assert data["summary"]["success"] == 2
