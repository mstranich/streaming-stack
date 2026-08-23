#!/usr/bin/env python3
"""Idempotent post-bootstrap configuration for the Servarr stack."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any


PROWLARR_URL = os.getenv("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_CONFIG = Path(
    os.getenv("PROWLARR_CONFIG", "/config/prowlarr/config.xml")
)
TRANSMISSION_NAME = os.getenv("PROWLARR_TRANSMISSION_NAME", "Transmission")
TRANSMISSION_HOST = os.getenv("TRANSMISSION_INTERNAL_HOST", "transmission")
TRANSMISSION_PORT = int(os.getenv("TRANSMISSION_INTERNAL_PORT", "9091"))
TRANSMISSION_URL_BASE = os.getenv(
    "TRANSMISSION_URL_BASE", "/transmission/"
)
TRANSMISSION_URL = os.getenv(
    "TRANSMISSION_URL", "http://transmission:9091"
).rstrip("/")
WAIT_SECONDS = int(os.getenv("CONFIGURE_WAIT_SECONDS", "120"))


class ConfigurationError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def read_prowlarr_api_key() -> str:
    try:
        root = ET.parse(PROWLARR_CONFIG).getroot()
    except (OSError, ET.ParseError) as error:
        raise ConfigurationError(
            f"Cannot read Prowlarr config at {PROWLARR_CONFIG}: {error}"
        ) from error

    api_key = root.findtext("ApiKey", "").strip()
    if not api_key:
        raise ConfigurationError("Prowlarr config does not contain an API key")
    return api_key


def request_json(
    method: str,
    path: str,
    api_key: str,
    payload: Any | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{PROWLARR_URL}{path}",
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise ConfigurationError(
                "Prowlarr API returned 401. Complete its initial Web "
                "authentication setup before running configure-stack."
            ) from error
        message = error.read().decode("utf-8", errors="replace")
        raise ConfigurationError(
            f"Prowlarr API {method} {path} failed with HTTP {error.code}: "
            f"{message[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise ConfigurationError(
            f"Cannot reach Prowlarr at {PROWLARR_URL}: {error.reason}"
        ) from error

    return None if not content else json.loads(content)


def wait_for_prowlarr() -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{PROWLARR_URL}/ping", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(2)

    raise ConfigurationError(
        f"Prowlarr did not become ready within {WAIT_SECONDS}s: {last_error}"
    )


def wait_for_transmission() -> None:
    username = required_env("TRANSMISSION_USER")
    password = required_env("TRANSMISSION_PASS")
    credentials = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    deadline = time.monotonic() + WAIT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{TRANSMISSION_URL}/transmission/web/",
            headers={"Authorization": f"Basic {credentials}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    return
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise ConfigurationError(
                    "Transmission rejected the credentials from .env"
                ) from error
            last_error = error
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(2)

    raise ConfigurationError(
        f"Transmission did not become ready within {WAIT_SECONDS}s: {last_error}"
    )


def set_field(resource: dict[str, Any], name: str, value: Any) -> None:
    for field in resource.get("fields", []):
        if str(field.get("name", "")).casefold() == name.casefold():
            field["value"] = value
            return
    raise ConfigurationError(
        f"Prowlarr Transmission schema does not contain field '{name}'"
    )


def transmission_resource(base: dict[str, Any]) -> dict[str, Any]:
    resource = deepcopy(base)
    resource["name"] = TRANSMISSION_NAME
    resource["enable"] = True
    resource.setdefault("priority", 1)
    resource.setdefault("tags", [])

    set_field(resource, "host", TRANSMISSION_HOST)
    set_field(resource, "port", TRANSMISSION_PORT)
    set_field(resource, "useSsl", False)
    set_field(resource, "urlBase", TRANSMISSION_URL_BASE)
    set_field(resource, "username", required_env("TRANSMISSION_USER"))
    set_field(resource, "password", required_env("TRANSMISSION_PASS"))
    return resource


def configure_prowlarr_transmission(api_key: str) -> None:
    existing_clients = request_json("GET", "/api/v1/downloadclient", api_key)
    existing = next(
        (
            client
            for client in existing_clients
            if str(client.get("implementation", "")).casefold() == "transmission"
            and str(client.get("name", "")).casefold()
            == TRANSMISSION_NAME.casefold()
        ),
        None,
    )

    if existing is None:
        schemas = request_json("GET", "/api/v1/downloadclient/schema", api_key)
        schema = next(
            (
                item
                for item in schemas
                if str(item.get("implementation", "")).casefold()
                == "transmission"
            ),
            None,
        )
        if schema is None:
            raise ConfigurationError("Prowlarr did not return a Transmission schema")
        resource = transmission_resource(schema)
        action = "create"
    else:
        resource = transmission_resource(existing)
        action = "update"

    request_json("POST", "/api/v1/downloadclient/test", api_key, resource)

    if action == "create":
        saved = request_json("POST", "/api/v1/downloadclient", api_key, resource)
    else:
        client_id = resource.get("id")
        if not client_id:
            raise ConfigurationError("Existing Transmission client has no id")
        saved = request_json(
            "PUT", f"/api/v1/downloadclient/{client_id}", api_key, resource
        )

    print(
        f"Prowlarr download client '{saved.get('name', TRANSMISSION_NAME)}' "
        f"{action}d and tested successfully."
    )


def configure_prowlarr_authentication(api_key: str) -> None:
    """Reconcile Prowlarr Web authentication with the shared Servarr credentials."""
    host_config = request_json("GET", "/api/v1/config/host", api_key)
    config_id = host_config.get("id")
    if not config_id:
        raise ConfigurationError("Prowlarr host configuration has no id")

    host_config["authenticationMethod"] = "forms"
    host_config["authenticationRequired"] = "disabledForLocalAddresses"
    host_config["username"] = required_env("SERVARR_USER")
    password = required_env("SERVARR_PASS")
    host_config["password"] = password
    host_config["passwordConfirmation"] = password

    request_json(
        "PUT", f"/api/v1/config/host/{config_id}", api_key, host_config
    )
    print("Prowlarr Web authentication reconciled successfully.")


def configure_prowlarr_ui(api_key: str) -> None:
    """Reconcile Prowlarr UI language with the shared Servarr preference."""
    language = required_env("SERVARR_UI_LANGUAGE")
    options = request_json("GET", "/api/v1/localization/options", api_key)
    valid_languages = {str(option.get("value", "")) for option in options}
    if language not in valid_languages:
        raise ConfigurationError(
            f"Unsupported SERVARR_UI_LANGUAGE '{language}'. Valid values: "
            + ", ".join(sorted(valid_languages))
        )

    ui_config = request_json("GET", "/api/v1/config/ui", api_key)
    config_id = ui_config.get("id")
    if not config_id:
        raise ConfigurationError("Prowlarr UI configuration has no id")

    ui_config["uiLanguage"] = language
    request_json("PUT", f"/api/v1/config/ui/{config_id}", api_key, ui_config)
    print(f"Prowlarr UI language reconciled successfully ({language}).")


def main() -> int:
    try:
        wait_for_prowlarr()
        wait_for_transmission()
        api_key = read_prowlarr_api_key()
        configure_prowlarr_transmission(api_key)
        configure_prowlarr_ui(api_key)
        configure_prowlarr_authentication(api_key)
    except ConfigurationError as error:
        print(f"Configuration failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
