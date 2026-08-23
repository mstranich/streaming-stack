#!/usr/bin/env python3
"""Create the shared Servarr data tree and normalize directory permissions."""

from __future__ import annotations

import os
from pathlib import Path


DIRECTORIES = (
    "torrents",
    "torrents/movies",
    "torrents/music",
    "torrents/books",
    "torrents/tv",
    "usenet",
    "usenet/movies",
    "usenet/music",
    "usenet/books",
    "usenet/tv",
    "media",
    "media/Movies",
    "media/Music",
    "media/Books",
    "media/TV",
)


def octal_env(name: str, default: str) -> int:
    value = os.getenv(name, default)
    try:
        return int(value, 8)
    except ValueError as error:
        raise SystemExit(f"{name} must be an octal value; received {value!r}") from error


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = Path(os.getenv("DATA_DIR", str(repo_root / "data")))
    puid = int(os.getenv("PUID", "1000"))
    pgid = int(os.getenv("PGID", "1000"))
    directory_mode = octal_env("DIRECTORY_MODE", "775")

    os.umask(octal_env("UMASK", "002"))

    for relative_path in DIRECTORIES:
        directory = data_dir / relative_path
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, puid, pgid)
        os.chmod(directory, directory_mode)

    print(f"Data directories initialized under {data_dir}")


if __name__ == "__main__":
    main()

