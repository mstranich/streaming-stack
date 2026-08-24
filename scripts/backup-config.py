#!/usr/bin/env python3
"""Create a checksummed backup of runtime configuration and local secrets."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("/source")
DESTINATION = Path("/backups")


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = DESTINATION / f"servarr-config-{stamp}.tar.gz"
    DESTINATION.mkdir(parents=True, exist_ok=True)
    if not (SOURCE / "config").is_dir() or not (SOURCE / ".env").is_file():
        raise SystemExit("Expected /source/config and /source/.env")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contains_secrets": True,
        "contents": ["config", ".env"],
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(SOURCE / "config", arcname="config", recursive=True)
        bundle.add(SOURCE / ".env", arcname=".env", recursive=False)
        manifest_info = tarfile.TarInfo("backup-manifest.json")
        manifest_info.size = len(manifest_bytes)
        manifest_info.mode = 0o600
        manifest_info.mtime = int(datetime.now(timezone.utc).timestamp())
        bundle.addfile(manifest_info, io.BytesIO(manifest_bytes))

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii"
    )
    print(f"Backup created: {archive.name}")
    print("WARNING: the archive contains API keys and passwords; store it securely.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
