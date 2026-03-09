"""DNS installer helpers for BIND9 slave and PowerDNS master."""

import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List

from tools.core.logger import get_logger


@dataclass
class InstallStep:
    """Single installation step execution result."""

    name: str
    command: str
    success: bool = False
    output: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "command": self.command,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class InstallReport:
    """Aggregate report for installation routine."""

    target: str
    dry_run: bool = False
    steps: List[InstallStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target": self.target,
            "dry_run": self.dry_run,
            "steps": [s.to_dict() for s in self.steps],
            "summary": {
                "total": len(self.steps),
                "success": sum(1 for s in self.steps if s.success),
                "failed": sum(1 for s in self.steps if not s.success),
            },
        }


class DNSInstaller:
    """Runs DNS server installation steps in a testable way."""

    def __init__(self, dry_run: bool = False, timeout: int = 300):
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = get_logger("dns.installer")

    def _run_shell_step(self, name: str, command: str) -> InstallStep:
        """Run shell step and capture result."""
        step = InstallStep(name=name, command=command)

        if self.dry_run:
            step.success = True
            step.output = "dry-run"
            return step

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True,
                timeout=self.timeout,
                check=False,
            )
            step.success = result.returncode == 0
            step.output = result.stdout.strip()
            step.error = result.stderr.strip() if result.returncode != 0 else ""
        except (subprocess.TimeoutExpired, Exception) as exc:
            step.success = False
            step.error = str(exc)

        return step

    def _execute_steps(self, target: str, steps: List[tuple]) -> InstallReport:
        """Execute sequence of named shell commands."""
        report = InstallReport(target=target, dry_run=self.dry_run)

        for name, command in steps:
            step = self._run_shell_step(name, command)
            report.steps.append(step)
            if not step.success and not self.dry_run:
                break

        return report

    def install_bind9_slave(
        self,
        zone: str,
        master_ip: str,
        zone_file: str = "/var/cache/bind/zones/{zone}.db",
    ) -> InstallReport:
        """Install and configure BIND9 as slave for one zone."""
        zone_path = zone_file.format(zone=zone)
        conf_block = (
            f"zone \"{zone}\" {{\\n"
            f"    type slave;\\n"
            f"    masters {{ {master_ip}; }};\\n"
            f"    file \"{zone_path}\";\\n"
            f"}};"
        )

        steps = [
            ("apt_update", "sudo apt update"),
            (
                "install_packages",
                "sudo apt install -y bind9 bind9-utils bind9-doc fail2ban ufw",
            ),
            (
                "create_zone_cache",
                "sudo mkdir -p /var/cache/bind/zones ; "
                "sudo chown -R bind:bind /var/cache/bind/zones",
            ),
            (
                "write_named_conf_local",
                f"printf '{conf_block}\\n' | sudo tee /etc/bind/named.conf.local",
            ),
            ("named_checkconf", "sudo named-checkconf"),
            ("enable_bind9", "sudo systemctl enable bind9"),
            ("restart_bind9", "sudo systemctl restart bind9"),
            ("enable_fail2ban", "sudo systemctl enable fail2ban"),
            ("restart_fail2ban", "sudo systemctl restart fail2ban"),
        ]

        return self._execute_steps("bind9-slave", steps)

    def install_pdns_master(
        self,
        slave_ip: str,
        db_root_password: str,
        db_pdns_password: str,
        api_key: str = "supersecreta",
    ) -> InstallReport:
        """Install and configure PowerDNS with MySQL backend."""
        mysql_setup = (
            "mysql -u root <<'SQL'\\n"
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{db_root_password}';\\n"
            "CREATE DATABASE IF NOT EXISTS pdns;\\n"
            f"CREATE USER IF NOT EXISTS 'pdns'@'localhost' IDENTIFIED BY '{db_pdns_password}';\\n"
            "GRANT ALL PRIVILEGES ON pdns.* TO 'pdns'@'localhost';\\n"
            "FLUSH PRIVILEGES;\\n"
            "SQL"
        )

        pdns_conf = (
            "launch=gmysql\\n\\n"
            "gmysql-host=127.0.0.1\\n"
            "gmysql-user=pdns\\n"
            f"gmysql-password={db_pdns_password}\\n"
            "gmysql-dbname=pdns\\n\\n"
            "api=yes\\n"
            f"api-key={api_key}\\n"
            "webserver=yes\\n"
            "webserver-address=127.0.0.1\\n"
            "webserver-port=8081\\n\\n"
            "master=yes\\n"
            "slave=no\\n"
            "disable-axfr=no\\n"
            f"allow-axfr-ips={slave_ip}\\n"
            f"also-notify={slave_ip}\\n"
        )

        steps = [
            ("apt_update", "sudo apt update && sudo apt -y upgrade"),
            (
                "install_packages",
                "sudo apt install -y pdns-server pdns-backend-mysql mariadb-server "
                "apache2 php libapache2-mod-php php-mysql php-xml php-intl php-mbstring "
                "php-curl unzip wget curl git",
            ),
            ("mysql_setup", mysql_setup),
            (
                "import_schema",
                "mysql -u pdns -p'"
                + db_pdns_password
                + "' pdns < /usr/share/pdns-backend-mysql/schema/schema.mysql.sql",
            ),
            (
                "write_pdns_conf",
                f"printf '{pdns_conf}' | sudo tee /etc/powerdns/pdns.conf",
            ),
            ("enable_pdns", "sudo systemctl enable pdns"),
            ("restart_pdns", "sudo systemctl restart pdns"),
        ]

        return self._execute_steps("pdns-master", steps)
