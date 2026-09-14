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
JACKETT_URL = os.getenv("JACKETT_URL", "http://jackett:9117").rstrip("/")
JACKETT_CONFIG = Path(
    os.getenv("JACKETT_CONFIG", "/config/jackett/Jackett/ServerConfig.json")
)
JACKETT_PROWLARR_TAG = os.getenv("JACKETT_PROWLARR_TAG", "jackett").strip()
FLARESOLVERR_URL = os.getenv(
    "FLARESOLVERR_URL", "http://flaresolverr:8191"
).rstrip("/")
FLARESOLVERR_NAME = os.getenv("PROWLARR_FLARESOLVERR_NAME", "FlareSolverr")
FLARESOLVERR_TAG = os.getenv("FLARESOLVERR_TAG", "flaresolver").strip()
FLARESOLVERR_REQUEST_TIMEOUT = int(os.getenv("FLARESOLVERR_REQUEST_TIMEOUT", "60"))
SONARR_URL = os.getenv("SONARR_URL", "http://sonarr:8989").rstrip("/")
SONARR_CONFIG = Path(os.getenv("SONARR_CONFIG", "/config/sonarr/config.xml"))
RADARR_URL = os.getenv("RADARR_URL", "http://radarr:7878").rstrip("/")
RADARR_CONFIG = Path(os.getenv("RADARR_CONFIG", "/config/radarr/config.xml"))
BAZARR_URL = os.getenv("BAZARR_URL", "http://bazarr:6767").rstrip("/")
BAZARR_CONFIG = Path(
    os.getenv("BAZARR_CONFIG", "/config/bazarr/config/config.yaml")
)
SEERR_URL = os.getenv("SEERR_URL", "http://seerr:5055").rstrip("/")
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


def read_jackett_api_key() -> str:
    try:
        config = json.loads(JACKETT_CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(
            f"Cannot read Jackett config at {JACKETT_CONFIG}: {error}"
        ) from error
    api_key = str(config.get("APIKey", "")).strip()
    if not api_key:
        raise ConfigurationError("Jackett config does not contain an API key")
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
    timeout: int = 15,
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
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
    except (urllib.error.URLError, TimeoutError) as error:
        reason = getattr(error, "reason", str(error))
        raise ConfigurationError(
            f"Cannot reach API at {base_url}: {reason}"
        ) from error

    return None if not content else json.loads(content)


def seerr_request_json(
    method: str, path: str, payload: Any | None = None, authenticated: bool = True
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if authenticated:
        headers["X-Api-Key"] = required_env("SEERR_API_KEY")
    request = urllib.request.Request(
        f"{SEERR_URL}{path}", data=body, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise ConfigurationError(
            f"Seerr API {method} {path} failed with HTTP {error.code}: "
            f"{message[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise ConfigurationError(
            f"Cannot reach Seerr at {SEERR_URL}: {error.reason}"
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


def wait_for_jackett() -> None:
    api_key = read_jackett_api_key()
    query = urllib.parse.urlencode({"apikey": api_key, "t": "caps"})
    health_url = (
        f"{JACKETT_URL}/api/v2.0/indexers/all/results/torznab/api?{query}"
    )
    deadline = time.monotonic() + WAIT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(2)
    raise ConfigurationError(
        f"Jackett did not become ready within {WAIT_SECONDS}s: {last_error}"
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


def transmission_rpc(method: str, arguments: dict[str, Any] | None = None) -> Any:
    username = required_env("TRANSMISSION_USER")
    password = required_env("TRANSMISSION_PASS")
    credentials = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = json.dumps(
        {"method": method, "arguments": arguments or {}}
    ).encode("utf-8")
    url = f"{TRANSMISSION_URL}/transmission/rpc"
    for _ in range(2):
        request = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 409:
                session_id = error.headers.get("X-Transmission-Session-Id")
                if session_id:
                    headers["X-Transmission-Session-Id"] = session_id
                    continue
            message = error.read().decode("utf-8", errors="replace")
            raise ConfigurationError(
                f"Transmission RPC {method} failed with HTTP {error.code}: "
                f"{message[:500]}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ConfigurationError(
                f"Cannot reach Transmission RPC at {url}: {error}"
            ) from error
        if result.get("result") != "success":
            raise ConfigurationError(
                f"Transmission RPC {method} failed: {result.get('result')}"
            )
        return result.get("arguments", {})
    raise ConfigurationError("Transmission RPC did not accept its session id")


def parse_minutes(value: str, variable: str) -> int:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as error:
        raise ConfigurationError(f"{variable} must use HH:MM") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ConfigurationError(f"{variable} must be a valid 24-hour time")
    return hour * 60 + minute


def configure_transmission_policy() -> None:
    session = transmission_rpc("session-get")
    seed_ratio = float(os.getenv("TRANSMISSION_SEED_RATIO", "2"))
    if seed_ratio <= 0:
        raise ConfigurationError("TRANSMISSION_SEED_RATIO must be greater than zero")

    day_bits = {"sun": 1, "mon": 2, "tue": 4, "wed": 8, "thu": 16, "fri": 32, "sat": 64}
    selected_days = [
        item.strip().casefold()
        for item in os.getenv("TRANSMISSION_WORK_DAYS", "mon,tue,wed,thu,fri").split(",")
        if item.strip()
    ]
    unknown_days = [item for item in selected_days if item not in day_bits]
    if not selected_days or unknown_days:
        raise ConfigurationError(
            "TRANSMISSION_WORK_DAYS contains invalid values: " + ", ".join(unknown_days)
        )
    day_mask = sum(day_bits[item] for item in set(selected_days))
    enabled = os.getenv("TRANSMISSION_WORK_SCHEDULE_ENABLED", "true").casefold() in {
        "1", "true", "yes", "on"
    }
    down = int(os.getenv("TRANSMISSION_WORK_DOWN_KBPS", "512"))
    up = int(os.getenv("TRANSMISSION_WORK_UP_KBPS", "128"))
    if down <= 0 or up <= 0:
        raise ConfigurationError("Transmission work-hour limits must be greater than zero")

    def key(snake: str, camel: str) -> str:
        return snake if snake in session else camel

    settings = {
        key("seed_ratio_limit", "seedRatioLimit"): seed_ratio,
        key("seed_ratio_limited", "seedRatioLimited"): True,
        key("alt_speed_time_enabled", "alt-speed-time-enabled"): enabled,
        key("alt_speed_time_day", "alt-speed-time-day"): day_mask,
        key("alt_speed_time_begin", "alt-speed-time-begin"): parse_minutes(
            os.getenv("TRANSMISSION_WORK_START", "09:00"), "TRANSMISSION_WORK_START"
        ),
        key("alt_speed_time_end", "alt-speed-time-end"): parse_minutes(
            os.getenv("TRANSMISSION_WORK_END", "18:00"), "TRANSMISSION_WORK_END"
        ),
        key("alt_speed_down", "alt-speed-down"): down,
        key("alt_speed_up", "alt-speed-up"): up,
    }
    transmission_rpc("session-set", settings)
    verified = transmission_rpc("session-get")
    for setting, expected in settings.items():
        if verified.get(setting) != expected:
            raise ConfigurationError(
                f"Transmission did not persist {setting}: expected {expected}, "
                f"got {verified.get(setting)}"
            )
    print(
        "Transmission policy reconciled: ratio "
        f"{seed_ratio:g}; work schedule {','.join(selected_days)} "
        f"{os.getenv('TRANSMISSION_WORK_START', '09:00')}-"
        f"{os.getenv('TRANSMISSION_WORK_END', '18:00')} at {down}/{up} kB/s."
    )


def set_field(resource: dict[str, Any], name: str, value: Any) -> None:
    for field in resource.get("fields", []):
        if str(field.get("name", "")).casefold() == name.casefold():
            field["value"] = value
            return
    raise ConfigurationError(
        f"Prowlarr schema does not contain field '{name}'"
    )


def set_optional_field(resource: dict[str, Any], name: str, value: Any) -> None:
    for field in resource.get("fields", []):
        if str(field.get("name", "")).casefold() == name.casefold():
            field["value"] = value
            return


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


def configure_prowlarr_flaresolverr(api_key: str) -> None:
    """Create or update Prowlarr's internal FlareSolverr indexer proxy."""
    if not FLARESOLVERR_TAG:
        raise ConfigurationError("FLARESOLVERR_TAG cannot be empty")
    tags = request_json("GET", "/api/v1/tag", api_key)
    tag = next(
        (item for item in tags
         if str(item.get("label", "")).casefold() == FLARESOLVERR_TAG.casefold()),
        None,
    )
    if tag is None:
        tag = request_json("POST", "/api/v1/tag", api_key, {"label": FLARESOLVERR_TAG})
    tag_id = tag.get("id")
    if not tag_id:
        raise ConfigurationError(f"Prowlarr tag '{FLARESOLVERR_TAG}' has no id")

    proxies = request_json("GET", "/api/v1/indexerproxy", api_key)
    existing = next(
        (
            proxy for proxy in proxies
            if str(proxy.get("implementation", "")).casefold() == "flaresolverr"
            and str(proxy.get("name", "")).casefold() == FLARESOLVERR_NAME.casefold()
        ),
        None,
    )
    if existing is None:
        schemas = request_json("GET", "/api/v1/indexerproxy/schema", api_key)
        schema = next(
            (item for item in schemas
             if str(item.get("implementation", "")).casefold() == "flaresolverr"),
            None,
        )
        if schema is None:
            raise ConfigurationError("Prowlarr did not return a FlareSolverr schema")
        resource = deepcopy(schema)
        method, path, action = "POST", "/api/v1/indexerproxy", "create"
    else:
        resource = deepcopy(existing)
        proxy_id = resource.get("id")
        if not proxy_id:
            raise ConfigurationError("Existing FlareSolverr proxy has no id")
        method, path, action = "PUT", f"/api/v1/indexerproxy/{proxy_id}", "update"

    resource["name"] = FLARESOLVERR_NAME
    resource["tags"] = [tag_id]
    set_field(resource, "host", FLARESOLVERR_URL)
    set_optional_field(resource, "requestTimeout", FLARESOLVERR_REQUEST_TIMEOUT)
    request_json("POST", "/api/v1/indexerproxy/test", api_key, resource)
    request_json(method, path, api_key, resource)
    print(
        f"Prowlarr indexer proxy '{FLARESOLVERR_NAME}' {action}d and tested "
        f"successfully with tag '{FLARESOLVERR_TAG}'."
    )


def get_or_create_prowlarr_tag(api_key: str, label: str) -> int:
    if not label:
        raise ConfigurationError("JACKETT_PROWLARR_TAG cannot be empty")
    tags = request_json("GET", "/api/v1/tag", api_key)
    tag = next(
        (item for item in tags if str(item.get("label", "")).casefold() == label.casefold()),
        None,
    )
    if tag is None:
        tag = request_json("POST", "/api/v1/tag", api_key, {"label": label})
    tag_id = tag.get("id")
    if not tag_id:
        raise ConfigurationError(f"Prowlarr tag '{label}' has no id")
    return int(tag_id)


def configured_jackett_indexers(api_key: str) -> list[dict[str, str]]:
    query = urllib.parse.urlencode(
        {"apikey": api_key, "t": "indexers", "configured": "true"}
    )
    url = f"{JACKETT_URL}/api/v2.0/indexers/all/results/torznab/api?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            root = ET.fromstring(response.read())
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
        raise ConfigurationError(f"Cannot discover Jackett indexers: {error}") from error

    discovered: list[dict[str, str]] = []
    for element in root.findall(".//indexer"):
        indexer_id = str(element.get("id", "")).strip()
        name = str(element.get("name", indexer_id)).strip()
        if indexer_id:
            discovered.append({"id": indexer_id, "name": name or indexer_id})

    requested = {
        item.strip().casefold()
        for item in os.getenv("JACKETT_SYNC_INDEXERS", "").split(",")
        if item.strip()
    }
    if requested:
        found = {item["id"].casefold() for item in discovered}
        missing = sorted(requested - found)
        if missing:
            raise ConfigurationError(
                "JACKETT_SYNC_INDEXERS contains IDs that are not configured in Jackett: "
                + ", ".join(missing)
            )
        discovered = [
            item for item in discovered if item["id"].casefold() in requested
        ]
    return discovered


def configure_prowlarr_jackett(api_key: str, jackett_key: str) -> None:
    """Expose selected Jackett trackers as individual Generic Torznab feeds."""
    desired = configured_jackett_indexers(jackett_key)
    tag_id = get_or_create_prowlarr_tag(api_key, JACKETT_PROWLARR_TAG)
    app_profiles = request_json("GET", "/api/v1/appprofile", api_key)
    requested_profile = os.getenv("JACKETT_PROWLARR_APP_PROFILE", "").strip()
    if requested_profile:
        app_profile = next(
            (
                item
                for item in app_profiles
                if str(item.get("name", "")).casefold()
                == requested_profile.casefold()
            ),
            None,
        )
        if app_profile is None:
            available = ", ".join(str(item.get("name")) for item in app_profiles)
            raise ConfigurationError(
                f"JACKETT_PROWLARR_APP_PROFILE '{requested_profile}' was not found. "
                f"Available profiles: {available}"
            )
    else:
        app_profile = next(
            (item for item in app_profiles if int(item.get("id", 0)) > 0), None
        )
    if app_profile is None:
        raise ConfigurationError("Prowlarr returned no usable App Profiles")
    app_profile_id = int(app_profile["id"])
    test_timeout = int(os.getenv("JACKETT_INDEXER_TEST_TIMEOUT", "120"))
    if test_timeout < 15:
        raise ConfigurationError("JACKETT_INDEXER_TEST_TIMEOUT must be at least 15")
    existing_indexers = request_json("GET", "/api/v1/indexer", api_key)
    managed = {
        str(item.get("name", ""))[len("Jackett / "):].casefold(): item
        for item in existing_indexers
        if str(item.get("name", "")).startswith("Jackett / ")
        and tag_id in item.get("tags", [])
    }
    native_names = {
        str(item.get("name", "")).casefold()
        for item in existing_indexers
        if item not in managed.values()
    }

    schemas = request_json(
        "GET", "/api/v1/indexer/schema", api_key, timeout=test_timeout
    )
    generic_schema = next(
        (item for item in schemas if str(item.get("name", "")) == "Generic Torznab"),
        None,
    )
    if generic_schema is None:
        raise ConfigurationError("Prowlarr did not return the Generic Torznab schema")

    desired_ids: set[str] = set()
    failed: list[str] = []
    for item in desired:
        indexer_id = item["id"]
        desired_ids.add(indexer_id.casefold())
        if item["name"].casefold() in native_names:
            current = managed.get(indexer_id.casefold())
            if current is not None:
                request_json("DELETE", f"/api/v1/indexer/{current['id']}", api_key)
            print(
                f"Jackett indexer '{item['name']}' skipped: an indexer with the "
                "same name already exists natively in Prowlarr."
            )
            continue
        current = managed.get(indexer_id.casefold())
        resource = deepcopy(current or generic_schema)
        resource["name"] = f"Jackett / {indexer_id}"
        resource["enable"] = True
        resource["appProfileId"] = app_profile_id
        resource.setdefault("priority", 25)
        resource["tags"] = sorted(set(resource.get("tags", [])) | {tag_id})
        set_field(
            resource,
            "baseUrl",
            f"{JACKETT_URL}/api/v2.0/indexers/{urllib.parse.quote(indexer_id, safe='')}/results/torznab",
        )
        set_field(resource, "apiPath", "/api")
        set_field(resource, "apiKey", jackett_key)
        try:
            request_json(
                "POST",
                "/api/v1/indexer/test",
                api_key,
                resource,
                timeout=test_timeout,
            )
        except ConfigurationError as error:
            failed.append(indexer_id)
            print(
                f"Jackett indexer '{indexer_id}' skipped after a failed Prowlarr "
                f"test: {error}"
            )
            continue
        if current is None:
            request_json("POST", "/api/v1/indexer", api_key, resource)
            action = "created"
        else:
            request_json(
                "PUT", f"/api/v1/indexer/{resource['id']}", api_key, resource
            )
            action = "updated"
        print(f"Prowlarr indexer 'Jackett / {indexer_id}' {action} and tested.")

    for indexer_id, stale in managed.items():
        if indexer_id not in desired_ids:
            request_json("DELETE", f"/api/v1/indexer/{stale['id']}", api_key)
            print(f"Removed stale Prowlarr indexer '{stale['name']}'.")

    if not desired:
        print(
            "Jackett has no configured indexers yet; add them at "
            "http://localhost:9117 and rerun configure-stack."
        )
    elif failed:
        print(
            "Jackett reconciliation completed with skipped failing indexers: "
            + ", ".join(failed)
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


def choose_profile(result: dict[str, Any], env_name: str, service: str) -> dict[str, Any]:
    profiles = result.get("profiles", [])
    requested = os.getenv(env_name, "").strip()
    if requested:
        profile = next(
            (item for item in profiles if str(item.get("name", "")).casefold() == requested.casefold()),
            None,
        )
        if profile is None:
            names = ", ".join(str(item.get("name")) for item in profiles)
            raise ConfigurationError(
                f"{env_name} '{requested}' was not found in {service}. Available: {names}"
            )
        return profile
    if not profiles:
        raise ConfigurationError(f"{service} returned no quality profiles")
    return profiles[0]


def configure_seerr_service(
    kind: str, api_key: str, root_folder: str, profile_env: str
) -> None:
    hostname = kind.lower()
    port = 7878 if kind == "Radarr" else 8989
    test_payload = {
        "name": kind,
        "hostname": hostname,
        "port": port,
        "apiKey": api_key,
        "useSsl": False,
        "baseUrl": "",
    }
    tested = seerr_request_json(
        "POST", f"/api/v1/settings/{hostname}/test", test_payload
    )
    profile = choose_profile(tested, profile_env, kind)
    folders = tested.get("rootFolders", [])
    if not any(str(item.get("path", "")).casefold() == root_folder.casefold() for item in folders):
        raise ConfigurationError(
            f"Seerr test did not find {kind} root folder {root_folder}"
        )
    resource = {
        **test_payload,
        "activeProfileId": profile["id"],
        "activeProfileName": profile["name"],
        "activeDirectory": root_folder,
        "is4k": False,
        "isDefault": True,
        "externalUrl": f"http://localhost:{port}",
        "syncEnabled": True,
        "preventSearch": False,
    }
    if kind == "Radarr":
        resource["minimumAvailability"] = "released"
    else:
        resource["enableSeasonFolders"] = True
    existing_items = seerr_request_json("GET", f"/api/v1/settings/{hostname}")
    existing = next(
        (item for item in existing_items if str(item.get("name", "")).casefold() == kind.casefold()),
        None,
    )
    if existing:
        resource = {**existing, **resource}
        resource.pop("id", None)
        seerr_request_json(
            "PUT", f"/api/v1/settings/{hostname}/{existing['id']}", resource
        )
        action = "updated"
    else:
        seerr_request_json("POST", f"/api/v1/settings/{hostname}", resource)
        action = "created"
    print(f"Seerr {kind} service {action} and tested ({profile['name']}).")


def configure_seerr(sonarr_key: str, radarr_key: str) -> None:
    public = seerr_request_json(
        "GET", "/api/v1/settings/public", authenticated=False
    )
    if not public.get("initialized"):
        print(
            "Seerr integration deferred: open http://localhost:5055 and complete "
            "the one-time Jellyfin administrator login, then rerun configure-stack."
        )
        return

    main_settings = seerr_request_json("GET", "/api/v1/settings/main")
    # The administrative GET includes the API key, but OpenAPI marks it
    # read-only and rejects it when the settings document is posted back.
    main_settings.pop("apiKey", None)
    main_settings["appLanguage"] = os.getenv("SEERR_UI_LANGUAGE", "es")
    main_settings["applicationTitle"] = os.getenv(
        "SEERR_APPLICATION_TITLE", "Seerr"
    )
    main_settings["localLogin"] = True
    seerr_request_json("POST", "/api/v1/settings/main", main_settings)

    jellyfin_key = required_env("JELLYFIN_API_KEY")
    jellyfin_settings = seerr_request_json(
        "POST",
        "/api/v1/settings/jellyfin",
        {
            "hostname": required_env("SEERR_JELLYFIN_INTERNAL_URL"),
            "externalHostname": required_env("SEERR_JELLYFIN_EXTERNAL_URL"),
            "apiKey": jellyfin_key,
        },
    )
    libraries = jellyfin_settings.get("libraries", [])
    previously_enabled = [
        str(library["id"])
        for library in libraries
        if library.get("enabled") and library.get("id")
    ]
    sync_query = urllib.parse.urlencode(
        {"sync": "true", "enable": ",".join(previously_enabled)}
    )
    try:
        libraries = seerr_request_json(
            "GET", f"/api/v1/settings/jellyfin/library?{sync_query}"
        )
    except ConfigurationError:
        if not libraries:
            raise
        print("Seerr Jellyfin library refresh failed; using saved libraries.")

    selected = [
        library
        for library in libraries
        if library.get("id")
        and str(library.get("type", "")).casefold()
        in {"movie", "show", "tvshows"}
    ]
    if not selected:
        raise ConfigurationError(
            "Seerr did not report any Jellyfin movie or TV libraries"
        )
    enabled_ids = [str(library["id"]) for library in selected]
    enable_query = urllib.parse.urlencode({"enable": ",".join(enabled_ids)})
    libraries = seerr_request_json(
        "GET", f"/api/v1/settings/jellyfin/library?{enable_query}"
    )
    enabled_after = {
        str(library["id"])
        for library in libraries
        if library.get("enabled") and library.get("id")
    }
    missing = [
        library.get("name", library["id"])
        for library in selected
        if str(library["id"]) not in enabled_after
    ]
    if missing:
        raise ConfigurationError(
            "Seerr did not enable Jellyfin libraries: " + ", ".join(missing)
        )
    print(
        "Seerr Jellyfin libraries enabled: "
        + ", ".join(str(library.get("name", library["id"])) for library in selected)
    )
    configure_seerr_service(
        "Radarr", radarr_key, "/data/media/Movies", "SEERR_RADARR_PROFILE"
    )
    configure_seerr_service(
        "Sonarr", sonarr_key, "/data/media/TV", "SEERR_SONARR_PROFILE"
    )
    print("Seerr Jellyfin libraries and general settings reconciled successfully.")


def main() -> int:
    try:
        if sys.argv[1:] == ["--only", "jackett"]:
            wait_for_application("Prowlarr", PROWLARR_URL)
            wait_for_jackett()
            prowlarr_key = read_api_key(PROWLARR_CONFIG, "Prowlarr")
            configure_prowlarr_jackett(prowlarr_key, read_jackett_api_key())
            return 0
        if sys.argv[1:] == ["--only", "seerr"]:
            wait_for_application("Sonarr", SONARR_URL)
            wait_for_application("Radarr", RADARR_URL)
            sonarr_key = read_api_key(SONARR_CONFIG, "Sonarr")
            radarr_key = read_api_key(RADARR_CONFIG, "Radarr")
            configure_seerr(sonarr_key, radarr_key)
            return 0
        if sys.argv[1:]:
            raise ConfigurationError(
                "Unsupported arguments. Use no arguments, --only jackett, "
                "or --only seerr"
            )
        wait_for_application("Prowlarr", PROWLARR_URL)
        wait_for_jackett()
        wait_for_application("Sonarr", SONARR_URL)
        wait_for_application("Radarr", RADARR_URL)
        wait_for_application("Bazarr", BAZARR_URL)
        wait_for_transmission()
        prowlarr_key = read_api_key(PROWLARR_CONFIG, "Prowlarr")
        jackett_key = read_jackett_api_key()
        sonarr_key = read_api_key(SONARR_CONFIG, "Sonarr")
        radarr_key = read_api_key(RADARR_CONFIG, "Radarr")
        configure_transmission_policy()
        # Configure the request front end first so an unrelated optional
        # integration failure cannot leave Seerr empty.
        configure_seerr(sonarr_key, radarr_key)
        configure_prowlarr_transmission(prowlarr_key)
        configure_prowlarr_flaresolverr(prowlarr_key)
        configure_prowlarr_jackett(prowlarr_key, jackett_key)
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
