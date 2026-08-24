#!/usr/bin/env python3
"""Restore a checksummed configuration backup after the stack is stopped."""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

BACKUPS = Path("/backups")
TARGET = Path("/restore")
ALLOWED_ROOTS = {"config", ".env", "backup-manifest.json"}


def safe_members(bundle: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = bundle.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise SystemExit(f"Unsafe archive member: {member.name}")
        if path.parts[0] not in ALLOWED_ROOTS or member.issym() or member.islnk():
            raise SystemExit(f"Unsupported archive member: {member.name}")
    return members


def verify_checksum(archive: Path) -> None:
    checksum_file = archive.with_suffix(archive.suffix + ".sha256")
    if not checksum_file.is_file():
        raise SystemExit(f"Missing checksum: {checksum_file.name}")
    expected = checksum_file.read_text(encoding="ascii").split()[0]
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit("Backup checksum mismatch; restore aborted")


def main() -> int:
    requested = os.environ.get("RESTORE_ARCHIVE", "").strip()
    if not requested or Path(requested).name != requested:
        raise SystemExit("Set RESTORE_ARCHIVE to a backup filename from ./backups")
    archive = BACKUPS / requested
    if not archive.is_file():
        raise SystemExit(f"Backup not found: {requested}")
    verify_checksum(archive)

    with tempfile.TemporaryDirectory() as temporary:
        extracted = Path(temporary)
        with tarfile.open(archive, "r:gz") as bundle:
            members = safe_members(bundle)
            bundle.extractall(extracted, members=members, filter="data")
        if not (extracted / "config").is_dir() or not (extracted / ".env").is_file():
            raise SystemExit("Backup is incomplete; restore aborted")

        for child in TARGET.joinpath("config").iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(extracted / "config", TARGET / "config", dirs_exist_ok=True)
        shutil.copy2(extracted / ".env", TARGET / ".env")

    print(f"Restored configuration from {requested}")
    print("Start the stack and run the diagnostic before normal use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
