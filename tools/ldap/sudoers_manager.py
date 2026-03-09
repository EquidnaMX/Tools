"""Gestión de reglas sudoers complementarias a autenticación LDAP."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import os
import subprocess
import tempfile


@dataclass
class SudoersRule:
    """Representa una regla sudoers para un grupo."""

    group: str
    run_as: str = "root"
    commands: str = "ALL"

    def to_line(self) -> str:
        """Convierte la regla al formato sudoers."""
        clean_group = self.group.lstrip("%")
        return f"%{clean_group} ALL=({self.run_as}) {self.commands}"


class SudoersManager:
    """Administrador de archivos en /etc/sudoers.d."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def create_rule_file(
        self,
        file_name: str,
        rule: SudoersRule,
        sudoers_dir: str = "/etc/sudoers.d",
        validate: bool = False,
        visudo_path: str = "visudo",
    ) -> Tuple[bool, str]:
        """Crea un archivo sudoers con una regla."""
        clean_name = file_name.strip()
        if not clean_name:
            return False, "El nombre del archivo no puede estar vacío"

        target_dir = Path(sudoers_dir)
        target_file = target_dir / clean_name

        content = self._build_file_content(rule)

        if validate:
            is_valid, message = self.validate_content(content, visudo_path=visudo_path)
            if not is_valid:
                return False, f"Validación sudoers falló: {message}"

        if self.dry_run:
            return True, f"[DRY-RUN] Se crearía {target_file} con: {rule.to_line()}"

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        os.chmod(target_file, 0o440)

        return True, f"Archivo creado: {target_file}"

    def list_rule_files(self, sudoers_dir: str = "/etc/sudoers.d") -> List[str]:
        """Lista archivos de reglas en el directorio sudoers."""
        target_dir = Path(sudoers_dir)
        if not target_dir.exists():
            return []

        files: List[str] = []
        for path in sorted(target_dir.iterdir()):
            if path.is_file():
                files.append(path.name)

        return files

    def remove_rule_file(self, file_name: str, sudoers_dir: str = "/etc/sudoers.d") -> Tuple[bool, str]:
        """Elimina un archivo de regla sudoers."""
        clean_name = file_name.strip()
        if not clean_name:
            return False, "El nombre del archivo no puede estar vacío"

        target_file = Path(sudoers_dir) / clean_name
        if not target_file.exists():
            return False, f"Archivo no encontrado: {target_file}"

        if self.dry_run:
            return True, f"[DRY-RUN] Se eliminaría {target_file}"

        target_file.unlink()
        return True, f"Archivo eliminado: {target_file}"

    def show_rule_file(self, file_name: str, sudoers_dir: str = "/etc/sudoers.d") -> Tuple[bool, str]:
        """Muestra el contenido de un archivo sudoers."""
        target_file = Path(sudoers_dir) / file_name.strip()
        if not target_file.exists():
            return False, f"Archivo no encontrado: {target_file}"

        return True, target_file.read_text(encoding="utf-8")

    def validate_content(self, content: str, visudo_path: str = "visudo") -> Tuple[bool, str]:
        """Valida contenido sudoers usando visudo -cf."""
        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                temp_path = tmp.name

            result = subprocess.run(
                [visudo_path, "-cf", temp_path],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return True, "OK"

            error_output = (result.stderr or result.stdout or "error desconocido").strip()
            return False, error_output
        except FileNotFoundError:
            return False, f"No se encontró '{visudo_path}' en el sistema"
        except Exception as exc:
            return False, str(exc)
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink(missing_ok=True)

    def _build_file_content(self, rule: SudoersRule) -> str:
        """Construye contenido completo del archivo sudoers."""
        return (
            "# Managed by tools-admin (LDAP sudoers helper)\n"
            f"{rule.to_line()}\n"
        )
