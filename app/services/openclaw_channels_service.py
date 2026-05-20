"""Wrapper around `openclaw channels` CLI for multi-account management.

Each channel (telegram/discord/slack/whatsapp/matrix/zalo) can host multiple
accounts identified by `account id`. Credentials are stored under
`~/.openclaw/channels/<channel>/<account>/` by openclaw, not in `.env`.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Final

from app.utils.dotenv_atomic import dotenv_get

log = logging.getLogger("openclaw.channels")

_OPENCLAW_BIN: Final[str] = "/usr/bin/openclaw"
_OPENCLAW_HOME: Final[str] = "/opt/openclaw"

# Short-lived cache for `channels list --json` — CLI takes 3-5s so panel reads
# of /api/channels were sluggish. 5s TTL keeps state near-real while removing
# the per-request cost.
_LIST_CACHE_TTL_S: Final[float] = 5.0
_list_cache: dict[str, Any] = {"ts": 0.0, "value": None}
_list_cache_lock = threading.Lock()

# UI-supported channels. Each entry maps internal id → display name + the CLI
# flag(s) used to pass credentials when adding an account.
SUPPORTED_CHANNELS: Final[dict[str, dict[str, Any]]] = {
    "telegram": {
        "label": "Telegram",
        "fields": [
            # Telegram CLI expects generic --token (not --bot-token).
            {"key": "token", "cli": "--token", "label": "Bot Token", "secret": True},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
    "discord": {
        "label": "Discord",
        "fields": [
            {"key": "token", "cli": "--token", "label": "Bot Token", "secret": True},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
    "slack": {
        "label": "Slack",
        "fields": [
            {"key": "token", "cli": "--token", "label": "Bot Token (xoxb-)", "secret": True},
            {"key": "app_token", "cli": "--app-token", "label": "App Token (xapp-)", "secret": True},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
    "whatsapp": {
        "label": "WhatsApp",
        "fields": [
            {"key": "http_url", "cli": "--http-url", "label": "HTTP Service URL", "secret": False},
            {"key": "token", "cli": "--token", "label": "Token / Credential", "secret": True},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
    "matrix": {
        "label": "Matrix",
        "fields": [
            {"key": "homeserver", "cli": "--homeserver", "label": "Homeserver URL", "secret": False},
            {"key": "user_id", "cli": "--user-id", "label": "User ID (@you:server)", "secret": False},
            {"key": "access_token", "cli": "--access-token", "label": "Access Token", "secret": True},
            {"key": "device_name", "cli": "--device-name", "label": "Device Name", "secret": False},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
    "zalo": {
        "label": "Zalo",
        "fields": [
            {"key": "token", "cli": "--token", "label": "Bot Token", "secret": True},
            {"key": "name", "cli": "--name", "label": "Tên hiển thị", "secret": False},
        ],
    },
}


def _gateway_env() -> dict[str, str]:
    """Env vars for invoking openclaw CLI as the gateway client."""
    token = dotenv_get("OPENCLAW_GATEWAY_TOKEN") or ""
    return {
        "HOME": _OPENCLAW_HOME,
        "OPENCLAW_GATEWAY_TOKEN": token,
    }


def _invalidate_cache() -> None:
    with _list_cache_lock:
        _list_cache["ts"] = 0.0
        _list_cache["value"] = None


def list_channels() -> dict[str, dict[str, Any]]:
    """Return `{channel: {accounts: [...], enabled, installed}}` for UI.

    Reads directly from the shared openclaw config — instant, no subprocess.
    The 5s cache is kept for repeat calls within a render burst.
    """
    with _list_cache_lock:
        now = time.time()
        if _list_cache["value"] is not None and now - _list_cache["ts"] < _LIST_CACHE_TTL_S:
            return _list_cache["value"]

    # Local import to avoid circular dependency.
    from app.services import openclaw_config_service

    cfg = openclaw_config_service.read()
    channels_cfg = cfg.get("channels", {}) if isinstance(cfg, dict) else {}

    out: dict[str, dict[str, Any]] = {}
    for ch in SUPPORTED_CHANNELS:
        meta = channels_cfg.get(ch, {}) if isinstance(channels_cfg, dict) else {}
        accounts_raw = meta.get("accounts", {}) if isinstance(meta, dict) else {}
        # `accounts` is a dict keyed by id in openclaw schema.
        account_ids = sorted(accounts_raw.keys()) if isinstance(accounts_raw, dict) else []
        out[ch] = {
            "label": SUPPORTED_CHANNELS[ch]["label"],
            "installed": bool(account_ids),
            "origin": "configured" if account_ids else "unknown",
            "fields": SUPPORTED_CHANNELS[ch]["fields"],
            "accounts": [{"id": a, "label": a} for a in account_ids],
        }
    with _list_cache_lock:
        _list_cache["ts"] = time.time()
        _list_cache["value"] = out
    return out


def _empty_channel() -> dict[str, Any]:
    return {"installed": False, "origin": "unknown", "accounts": [], "fields": []}


_CLI_TO_CONFIG_KEY: Final[dict[str, str]] = {
    "token": "botToken",
    "app_token": "appToken",
    "http_url": "httpUrl",
    "access_token": "accessToken",
    "user_id": "userId",
    "device_name": "deviceName",
    "homeserver": "homeserver",
    "name": "name",
}


def add_account(channel: str, account_id: str, fields: dict[str, str]) -> tuple[bool, str]:
    """Write the account directly into the shared config (hot-reload picks up).

    Direct write avoids the ~6s `openclaw channels add` subprocess and the
    ConfigMutationConflictError that occurs when openclaw caches a stale view.
    """
    if channel not in SUPPORTED_CHANNELS:
        return False, f"Channel '{channel}' not supported"
    if not account_id or not _valid_account_id(account_id):
        return False, "account id must match [a-z0-9_-]{1,64}"

    from app.services import openclaw_config_service

    schema = SUPPORTED_CHANNELS[channel]["fields"]
    entry: dict[str, Any] = {"name": fields.get("name") or account_id, "enabled": True}
    for f in schema:
        val = fields.get(f["key"])
        if val and f["key"] != "name":
            cfg_key = _CLI_TO_CONFIG_KEY.get(f["key"], f["key"])
            entry[cfg_key] = str(val)

    cfg = openclaw_config_service.read()
    cfg.setdefault("channels", {})
    cfg["channels"].setdefault(channel, {"enabled": True, "accounts": {}})
    cfg["channels"][channel]["enabled"] = True
    cfg["channels"][channel].setdefault("accounts", {})
    cfg["channels"][channel]["accounts"][account_id] = entry
    openclaw_config_service.write_atomic(cfg)
    _invalidate_cache()
    return True, f"Added {channel} account '{account_id}'"


def remove_account(channel: str, account_id: str) -> tuple[bool, str]:
    """Remove account directly from shared config (hot-reload triggers shutdown).

    Direct write is ~100ms vs ~20s for `openclaw channels remove --delete`.
    Openclaw watches the file and gracefully stops the provider on next reload.
    """
    if channel not in SUPPORTED_CHANNELS:
        return False, f"Channel '{channel}' not supported"
    if not _valid_account_id(account_id):
        return False, "invalid account id"

    from app.services import openclaw_config_service

    cfg = openclaw_config_service.read()
    accounts = (
        cfg.get("channels", {}).get(channel, {}).get("accounts", {})
        if isinstance(cfg.get("channels"), dict)
        else {}
    )
    if not isinstance(accounts, dict) or account_id not in accounts:
        return False, f"Account '{account_id}' not found"
    del accounts[account_id]
    # If no accounts left, also disable the channel entry to stop crash loops.
    if not accounts:
        cfg["channels"][channel] = {"enabled": False, "accounts": {}}
    openclaw_config_service.write_atomic(cfg)
    _invalidate_cache()
    return True, f"Removed {channel} account '{account_id}'"


def _valid_account_id(s: str) -> bool:
    import re

    return bool(re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", s))


def supported_channels_meta() -> dict[str, dict[str, Any]]:
    """For UI to render schema (field labels + secret flags) per channel."""
    return {
        ch: {"label": meta["label"], "fields": meta["fields"]}
        for ch, meta in SUPPORTED_CHANNELS.items()
    }
