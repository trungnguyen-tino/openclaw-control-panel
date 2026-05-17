"""Messaging-channel config (Telegram, Discord, Slack, Zalo).

State split:
- bot tokens → `.env`
- enabled flag + dmPolicy → `openclaw.json.channels[<ch>]`
"""

from __future__ import annotations

from typing import Any, Final

from app.services import openclaw_config_service
from app.utils.dotenv_atomic import dotenv_get, dotenv_set, dotenv_unset
from app.utils.secrets_mask import sanitize_key

CHANNELS: Final[dict[str, dict[str, list[str] | bool]]] = {
    "telegram": {"env_keys": ["TELEGRAM_BOT_TOKEN"], "supports_app_token": False},
    "discord": {"env_keys": ["DISCORD_BOT_TOKEN"], "supports_app_token": False},
    "slack": {"env_keys": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"], "supports_app_token": True},
    "zalo": {"env_keys": ["ZALO_BOT_TOKEN"], "supports_app_token": False},
}


def list_status() -> dict[str, dict[str, Any]]:
    cfg = openclaw_config_service.read()
    channels_cfg = cfg.get("channels", {})
    out: dict[str, dict[str, Any]] = {}
    for ch, meta in CHANNELS.items():
        env_keys = list(meta["env_keys"])  # type: ignore[arg-type]
        tokens = {k: dotenv_get(k) for k in env_keys}
        out[ch] = {
            "enabled": bool(channels_cfg.get(ch, {}).get("enabled")),
            "dmPolicy": channels_cfg.get(ch, {}).get("dmPolicy"),
            "tokens": {k: sanitize_key(v) if v else None for k, v in tokens.items()},
            "configured": all(tokens.values()),
        }
    return out


def upsert(
    channel: str,
    token: str,
    app_token: str | None = None,
    dm_policy: str | None = None,
) -> tuple[bool, str]:
    if channel not in CHANNELS:
        return False, f"Unknown channel '{channel}'"
    meta = CHANNELS[channel]
    env_keys = list(meta["env_keys"])  # type: ignore[arg-type]
    dotenv_set(env_keys[0], token)
    if meta.get("supports_app_token") and app_token:
        dotenv_set(env_keys[1], app_token)
    cfg = openclaw_config_service.read()
    channels_cfg = cfg.setdefault("channels", {})
    entry = channels_cfg.setdefault(channel, {})
    entry["enabled"] = True
    if dm_policy:
        entry["dmPolicy"] = dm_policy
    openclaw_config_service.write_atomic(cfg)
    return True, channel


def delete(channel: str) -> tuple[bool, str]:
    if channel not in CHANNELS:
        return False, f"Unknown channel '{channel}'"
    meta = CHANNELS[channel]
    for k in meta["env_keys"]:  # type: ignore[union-attr]
        dotenv_unset(k)
    cfg = openclaw_config_service.read()
    channels_cfg = cfg.setdefault("channels", {})
    if channel in channels_cfg:
        channels_cfg[channel]["enabled"] = False
    openclaw_config_service.write_atomic(cfg)
    return True, channel
