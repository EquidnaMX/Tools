from pathlib import Path

from click.testing import CliRunner

from tools.cli.backup_commands import backup


def test_backup_create_and_list(tmp_path: Path):
    runner = CliRunner()

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("x")

    backup_dir = tmp_path / "backups"

    result_create = runner.invoke(
        backup,
        [
            "create",
            str(source),
            "--backup-dir",
            str(backup_dir),
            "--name",
            "cli",
            "--keep",
            "2",
        ],
    )
    assert result_create.exit_code == 0

    result_list = runner.invoke(
        backup,
        ["list", "--backup-dir", str(backup_dir), "--prefix", "cli"],
    )
    assert result_list.exit_code == 0
    assert ".tar.gz" in result_list.output
