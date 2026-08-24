#!/usr/bin/env python3
"""Run secret-safe network, API, storage and external Jellyfin checks."""

from __future__ import annotations

import base64
import os
import shutil
import socket
import urllib.error
import urllib.request
from pathlib import Path

SERVICES = {
    "Transmission": ("transmission", 9091, "/transmission/web/"),
    "Prowlarr": ("prowlarr", 9696, "/ping"),
    "FlareSolverr": ("flaresolverr", 8191, "/"),
    "Sonarr": ("sonarr", 8989, "/ping"),
    "Radarr": ("radarr", 7878, "/ping"),
    "Bazarr": ("bazarr", 6767, "/"),
    "Seerr": ("seerr", 5055, "/api/v1/settings/public"),
}


def check_http(name: str, host: str, port: int, path: str) -> None:
    socket.getaddrinfo(host, port)
    request = urllib.request.Request(f"http://{host}:{port}{path}")
    if name == "Transmission":
        credentials = f"{os.environ['TRANSMISSION_USER']}:{os.environ['TRANSMISSION_PASS']}"
        token = base64.b64encode(credentials.encode()).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}")


def main() -> int:
    failures: list[str] = []
    for name, (host, port, path) in SERVICES.items():
        try:
            check_http(name, host, port, path)
            print(f"[OK] {name}: DNS and HTTP")
        except Exception as error:
            failures.append(name)
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")

    jellyfin_host = os.getenv("JELLYFIN_HOST", "host.docker.internal")
    jellyfin_port = int(os.getenv("JELLYFIN_PORT", "8096"))
    try:
        check_http("Jellyfin", jellyfin_host, jellyfin_port, "/System/Info/Public")
        print("[OK] Jellyfin externo: DNS and HTTP")
    except Exception as error:
        failures.append("Jellyfin")
        print(f"[FAIL] Jellyfin: {type(error).__name__}: {error}")

    required = [
        Path("/data/torrents/movies"), Path("/data/torrents/tv"),
        Path("/data/media/Movies"), Path("/data/media/TV"),
    ]
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        failures.append("data-layout")
        print("[FAIL] Missing data directories: " + ", ".join(missing))
    else:
        print("[OK] Shared /data layout")

    free_gb = shutil.disk_usage("/data").free / (1024 ** 3)
    minimum = float(os.getenv("MIN_FREE_SPACE_GB", "20"))
    if free_gb < minimum:
        failures.append("free-space")
        print(f"[FAIL] Free space {free_gb:.1f} GiB is below {minimum:.1f} GiB")
    else:
        print(f"[OK] Free space: {free_gb:.1f} GiB")

    print(f"Diagnostic completed: {len(failures)} failure(s). No secrets printed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
