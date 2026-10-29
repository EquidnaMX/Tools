"""Exercise the public restore boundary with real, isolated archives."""

import io
import tarfile

import pytest

from tools.backup import BackupError, BackupManager


def archive_with(tmp_path, member):
    archive = tmp_path / "input.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        root = tarfile.TarInfo("source")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        tar.addfile(member, io.BytesIO(b"x") if member.isfile() else None)
    return archive


@pytest.mark.parametrize(
    "name",
    [
        "../restore-sibling/proof",
        "/absolute-proof",
        "C:\\outside",
        "source\\..\\outside",
    ],
)
def test_restore_rejects_escaping_names(tmp_path, name):
    member = tarfile.TarInfo(name)
    member.size = 1
    archive = archive_with(tmp_path, member)
    manager = BackupManager(tmp_path / "backups")
    with pytest.raises(BackupError):
        manager.restore_backup(archive, tmp_path / "restore")
    assert not (tmp_path / "restore-sibling").exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_restore_rejects_escaping_links_and_special_files(tmp_path, kind):
    member = tarfile.TarInfo("source/link")
    member.type = kind
    member.linkname = "../../outside"
    archive = archive_with(tmp_path, member)
    with pytest.raises(BackupError):
        BackupManager(tmp_path / "backups").restore_backup(
            archive, tmp_path / "restore"
        )
    assert not (tmp_path / "outside").exists()


def test_restore_rejects_existing_destination_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "restore"
    source = destination / "source"
    source.mkdir(parents=True)
    try:
        (source / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted on this platform")
    member = tarfile.TarInfo("source/link/proof")
    member.size = 1
    archive = archive_with(tmp_path, member)
    with pytest.raises(BackupError):
        BackupManager(tmp_path / "backups").restore_backup(
            archive, destination, overwrite=True
        )
    assert not (outside / "proof").exists()


def test_restore_preserves_safe_relative_links(tmp_path):
    archive = tmp_path / "links.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        file = tarfile.TarInfo("source/file")
        file.size = 1
        tar.addfile(file, io.BytesIO(b"x"))
        for name, kind, target in [
            ("sym", tarfile.SYMTYPE, "file"),
            ("hard", tarfile.LNKTYPE, "source/file"),
        ]:
            link = tarfile.TarInfo("source/" + name)
            link.type, link.linkname = kind, target
            tar.addfile(link)
    root = BackupManager(tmp_path / "backups").restore_backup(
        archive, tmp_path / "restore"
    )
    assert (root / "sym").read_bytes() == b"x"
    assert (root / "hard").read_bytes() == b"x"


def test_restore_filters_again_after_archive_creates_symlink(tmp_path):
    """An archive-created link must not redirect a later file outside restore."""
    archive = tmp_path / "chain.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("source/link")
        link.type, link.linkname = tarfile.SYMTYPE, "../../outside"
        tar.addfile(link)
        file = tarfile.TarInfo("source/link/proof")
        file.size = 1
        tar.addfile(file, io.BytesIO(b"x"))
    with pytest.raises(BackupError):
        BackupManager(tmp_path / "backups").restore_backup(
            archive, tmp_path / "restore"
        )
    assert not (tmp_path / "outside").exists()
