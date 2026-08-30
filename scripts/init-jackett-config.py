#!/usr/bin/env python3
"""Create or reconcile Jackett's bootstrap server configuration."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


CONFIG = Path("/config/jackett/Jackett/ServerConfig.json")


def defaults() -> dict[str, object]:
    return {
        "Port": 9117,
        "LocalBindAddress": "127.0.0.1",
        "AllowExternal": True,
        "AllowCORS": False,
        "APIKey": secrets.token_hex(16),
        "AdminPassword": None,
        "InstanceId": secrets.token_urlsafe(48),
        "BlackholeDir": "",
        "UpdateDisabled": True,
        "UpdatePrerelease": False,
        "BasePathOverride": "",
        "BaseUrlOverride": "",
        "CacheEnabled": True,
        "CacheTtl": 2100,
        "CacheMaxResultsPerIndexer": 1000,
        "FlareSolverrUrl": "",
        "FlareSolverrMaxTimeout": 60000,
        "OmdbApiKey": "",
        "OmdbApiUrl": "",
        "ProxyType": -1,
        "ProxyUrl": "",
        "ProxyPort": None,
        "ProxyUsername": "",
        "ProxyPassword": "",
        "ProxyIsAnonymous": True,
    }


def main() -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config = defaults()
    previous: dict[str, object] | None = None
    if CONFIG.exists():
        previous = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        config.update(previous)

    timeout = int(os.getenv("JACKETT_FLARESOLVERR_MAX_TIMEOUT", "60000"))
    if timeout < 5000:
        raise ValueError("JACKETT_FLARESOLVERR_MAX_TIMEOUT must be at least 5000")
    config["FlareSolverrUrl"] = os.getenv(
        "JACKETT_FLARESOLVERR_URL", "http://flaresolverr:8191"
    ).rstrip("/")
    config["FlareSolverrMaxTimeout"] = timeout
    config["UpdateDisabled"] = True

    if config != previous:
        temporary = CONFIG.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        temporary.replace(CONFIG)
        print("Jackett server configuration reconciled (FlareSolverr enabled).")
    else:
        print("Jackett server configuration already matches the desired state.")


if __name__ == "__main__":
    main()
