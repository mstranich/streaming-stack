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
import urllib.parse
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any


PROWLARR_URL = os.getenv("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_CONFIG = Path(
    os.getenv("PROWLARR_CONFIG", "/config/prowlarr/config.xml")
)
SONARR_URL = os.getenv("SONARR_URL", "http://sonarr:8989").rstrip("/")
SONARR_CONFIG = Path(os.getenv("SONARR_CONFIG", "/config/sonarr/config.xml"))
RADARR_URL = os.getenv("RADARR_URL", "http://radarr:7878").rstrip("/")
RADARR_CONFIG = Path(os.getenv("RADARR_CONFIG", "/config/radarr/config.xml"))
BAZARR_URL = os.getenv("BAZARR_URL", "http://bazarr:6767").rstrip("/")
BAZARR_CONFIG = Path(
    os.getenv("BAZARR_CONFIG", "/config/bazarr/config/config.yaml")
)
JELLYFIN_HOST = os.getenv("JELLYFIN_HOST", "host.docker.internal")
JELLYFIN_PORT = int(os.getenv("JELLYFIN_PORT", "8096"))
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
ARR_UI_LANGUAGE_IDS = {
    "en": 1,
    "en_US": 1,
    "es": 3,
    "es_ES": 3,
    "es_MX": 34,
}


class ConfigurationError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def read_api_key(config_path: Path, application: str) -> str:
    try:
        root = ET.parse(config_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ConfigurationError(
            f"Cannot read {application} config at {config_path}: {error}"
        ) from error

    api_key = root.findtext("ApiKey", "").strip()
    if not api_key:
        raise ConfigurationError(f"{application} config does not contain an API key")
    return api_key


def read_bazarr_api_key() -> str:
    try:
        content = BAZARR_CONFIG.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Cannot read Bazarr config: {error}") from error
    in_auth = False
    for line in content.splitlines():
        if line == "auth:":
            in_auth = True
        elif in_auth and line and not line.startswith(" "):
            break
        elif in_auth and line.strip().startswith("apikey:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    raise ConfigurationError("Bazarr config does not contain an API key")


def request_json(
    method: str,
    path: str,
    api_key: str,
    payload: Any | None = None,
    base_url: str = PROWLARR_URL,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
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


def wait_for_application(name: str, base_url: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/ping", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(2)

    raise ConfigurationError(
        f"{name} did not become ready within {WAIT_SECONDS}s: {last_error}"
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


def configure_arr_web(name: str, base_url: str, api_key: str) -> None:
    """Apply the shared UI language and local-address authentication policy."""
    language = required_env("SERVARR_UI_LANGUAGE")
    language_id = ARR_UI_LANGUAGE_IDS.get(language)
    if language_id is None:
        raise ConfigurationError(
            f"SERVARR_UI_LANGUAGE '{language}' has no Sonarr/Radarr numeric mapping"
        )
    ui_config = request_json(
        "GET", "/api/v3/config/ui", api_key, base_url=base_url
    )
    ui_config["uiLanguage"] = language_id
    request_json(
        "PUT",
        f"/api/v3/config/ui/{ui_config['id']}",
        api_key,
        ui_config,
        base_url,
    )

    host_config = request_json(
        "GET", "/api/v3/config/host", api_key, base_url=base_url
    )
    host_config["authenticationMethod"] = "forms"
    host_config["authenticationRequired"] = "disabledForLocalAddresses"
    host_config["username"] = required_env("SERVARR_USER")
    password = required_env("SERVARR_PASS")
    host_config["password"] = password
    host_config["passwordConfirmation"] = password
    request_json(
        "PUT",
        f"/api/v3/config/host/{host_config['id']}",
        api_key,
        host_config,
        base_url,
    )
    print(f"{name} Web authentication and UI language reconciled ({language}).")


def configure_arr_root_folder(
    name: str, base_url: str, api_key: str, folder: str
) -> None:
    roots = request_json("GET", "/api/v3/rootfolder", api_key, base_url=base_url)
    if not any(str(root.get("path", "")).casefold() == folder.casefold() for root in roots):
        request_json(
            "POST", "/api/v3/rootfolder", api_key, {"path": folder}, base_url
        )
        print(f"{name} root folder created: {folder}")


def configure_arr_transmission(
    name: str, base_url: str, api_key: str, category_field: str, category: str
) -> None:
    clients = request_json("GET", "/api/v3/downloadclient", api_key, base_url=base_url)
    existing = next(
        (item for item in clients if str(item.get("implementation", "")).casefold() == "transmission"),
        None,
    )
    if existing is None:
        schemas = request_json(
            "GET", "/api/v3/downloadclient/schema", api_key, base_url=base_url
        )
        resource = deepcopy(next(
            item for item in schemas
            if str(item.get("implementation", "")).casefold() == "transmission"
        ))
        action = "POST"
        path = "/api/v3/downloadclient"
    else:
        resource = deepcopy(existing)
        action = "PUT"
        path = f"/api/v3/downloadclient/{resource['id']}"
    resource["name"] = "Transmission"
    resource["enable"] = True
    resource.setdefault("priority", 1)
    resource.setdefault("tags", [])
    set_field(resource, "host", TRANSMISSION_HOST)
    set_field(resource, "port", TRANSMISSION_PORT)
    set_field(resource, "useSsl", False)
    set_field(resource, "urlBase", TRANSMISSION_URL_BASE)
    set_field(resource, "username", required_env("TRANSMISSION_USER"))
    set_field(resource, "password", required_env("TRANSMISSION_PASS"))
    set_field(resource, category_field, category)
    request_json(
        "POST", "/api/v3/downloadclient/test", api_key, resource, base_url
    )
    request_json(action, path, api_key, resource, base_url)
    print(f"{name} Transmission client reconciled and tested ({category}).")


def configure_prowlarr_application(
    prowlarr_key: str, app_name: str, app_url: str, app_key: str
) -> None:
    applications = request_json("GET", "/api/v1/applications", prowlarr_key)
    existing = next(
        (item for item in applications if str(item.get("implementation", "")).casefold() == app_name.casefold()),
        None,
    )
    if existing is None:
        schemas = request_json("GET", "/api/v1/applications/schema", prowlarr_key)
        resource = deepcopy(next(
            item for item in schemas
            if str(item.get("implementation", "")).casefold() == app_name.casefold()
        ))
        method, path = "POST", "/api/v1/applications"
    else:
        resource = deepcopy(existing)
        method, path = "PUT", f"/api/v1/applications/{resource['id']}"
    resource["name"] = app_name
    resource["syncLevel"] = "fullSync"
    resource.setdefault("tags", [])
    set_field(resource, "prowlarrUrl", PROWLARR_URL)
    set_field(resource, "baseUrl", app_url)
    set_field(resource, "apiKey", app_key)
    request_json("POST", "/api/v1/applications/test", prowlarr_key, resource)
    request_json(method, path, prowlarr_key, resource)
    print(f"Prowlarr application '{app_name}' reconciled and tested.")


def configure_bazarr(sonarr_key: str, radarr_key: str) -> None:
    """Connect Bazarr to Sonarr/Radarr using its form-encoded settings API."""
    bazarr_key = read_bazarr_api_key()
    settings = {
        "settings-general-use_sonarr": "true",
        "settings-sonarr-ip": "sonarr",
        "settings-sonarr-port": "8989",
        "settings-sonarr-base_url": "/",
        "settings-sonarr-ssl": "false",
        "settings-sonarr-apikey": sonarr_key,
        "settings-general-use_radarr": "true",
        "settings-radarr-ip": "radarr",
        "settings-radarr-port": "7878",
        "settings-radarr-base_url": "/",
        "settings-radarr-ssl": "false",
        "settings-radarr-apikey": radarr_key,
    }
    jellyfin_key = os.getenv("JELLYFIN_API_KEY", "").strip()
    if jellyfin_key:
        settings.update({
            "settings-general-use_jellyfin": "true",
            "settings-jellyfin-url": f"http://{JELLYFIN_HOST}:{JELLYFIN_PORT}",
            "settings-jellyfin-apikey": jellyfin_key,
            "settings-jellyfin-refresh_method": "immediate",
        })
    form = urllib.parse.urlencode(settings).encode("utf-8")
    request = urllib.request.Request(
        f"{BAZARR_URL}/api/system/settings",
        data=form,
        method="POST",
        headers={
            "X-API-KEY": bazarr_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 204:
                raise ConfigurationError(
                    f"Bazarr settings returned unexpected HTTP {response.status}"
                )
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise ConfigurationError(
            f"Bazarr settings failed with HTTP {error.code}: {message[:500]}"
        ) from error
    print("Bazarr connections to Sonarr and Radarr reconciled successfully.")
    if not jellyfin_key:
        print("Bazarr Jellyfin integration skipped: JELLYFIN_API_KEY is empty.")
        return

    jellyfin_url = f"http://{JELLYFIN_HOST}:{JELLYFIN_PORT}"
    test_body = urllib.parse.urlencode(
        {"url": jellyfin_url, "apikey": jellyfin_key}
    ).encode("utf-8")
    test = urllib.request.Request(
        f"{BAZARR_URL}/api/jellyfin/test-connection",
        data=test_body,
        method="POST",
        headers={
            "X-API-KEY": bazarr_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(test, timeout=30) as response:
            if response.status != 200:
                raise ConfigurationError(
                    f"Bazarr Jellyfin test returned HTTP {response.status}"
                )
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise ConfigurationError(
            f"Bazarr Jellyfin test failed with HTTP {error.code}: {message[:500]}"
        ) from error
    print(
        "Bazarr connection to external Jellyfin reconciled and tested "
        f"({JELLYFIN_HOST}:{JELLYFIN_PORT})."
    )


def main() -> int:
    try:
        wait_for_application("Prowlarr", PROWLARR_URL)
        wait_for_application("Sonarr", SONARR_URL)
        wait_for_application("Radarr", RADARR_URL)
        wait_for_application("Bazarr", BAZARR_URL)
        wait_for_transmission()
        prowlarr_key = read_api_key(PROWLARR_CONFIG, "Prowlarr")
        sonarr_key = read_api_key(SONARR_CONFIG, "Sonarr")
        radarr_key = read_api_key(RADARR_CONFIG, "Radarr")
        configure_prowlarr_transmission(prowlarr_key)
        configure_prowlarr_ui(prowlarr_key)
        configure_prowlarr_authentication(prowlarr_key)
        configure_arr_web("Sonarr", SONARR_URL, sonarr_key)
        configure_arr_root_folder("Sonarr", SONARR_URL, sonarr_key, "/data/media/TV")
        configure_arr_transmission("Sonarr", SONARR_URL, sonarr_key, "tvCategory", "tv")
        configure_arr_web("Radarr", RADARR_URL, radarr_key)
        configure_arr_root_folder("Radarr", RADARR_URL, radarr_key, "/data/media/Movies")
        configure_arr_transmission("Radarr", RADARR_URL, radarr_key, "movieCategory", "movies")
        configure_prowlarr_application(prowlarr_key, "Sonarr", SONARR_URL, sonarr_key)
        configure_prowlarr_application(prowlarr_key, "Radarr", RADARR_URL, radarr_key)
        configure_bazarr(sonarr_key, radarr_key)
    except ConfigurationError as error:
        print(f"Configuration failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
