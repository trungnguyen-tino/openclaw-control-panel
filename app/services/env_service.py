"""Env-var introspection + safe mutation for `/api/env/*` endpoints."""

from __future__ import annotations

from typing import Final

from app.services import openclaw_config_service
from app.utils.dotenv_atomic import dotenv_read, dotenv_set, dotenv_unset
from app.utils.secrets_mask import mask_env_value

LOCKED_DELETE: Final[frozenset[str]] = frozenset(
    {
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_MGMT_API_KEY",
        "OPENCLAW_VERSION",
        "OPENCLAW_GATEWAY_PORT",
    }
)

LOCKED_SET: Final[frozenset[str]] = frozenset({"OPENCLAW_MGMT_API_KEY"})


def list_masked() -> dict[str, str]:
    env = dotenv_read()
    return {k: mask_env_value(k, v) for k, v in env.items()}


def set_value(key: str, value: str) -> tuple[bool, str]:
    if key in LOCKED_SET:
        return False, f"{key} cannot be modified via API"
    dotenv_set(key, value)
    if key == "OPENCLAW_GATEWAY_TOKEN":
        # Keep gateway/auth/token in sync with .env so the running gateway
        # picks up the new token on the next restart.
        try:
            cfg = openclaw_config_service.read()
            gw = cfg.setdefault("gateway", {}).setdefault("auth", {})
            gw["token"] = value
            openclaw_config_service.write_atomic(cfg)
        # Best-effort openclaw.json sync; .env write already succeeded.
        except Exception:  # noqa: BLE001, S110
            pass
    return True, key


def delete_value(key: str) -> tuple[bool, str]:
    if key in LOCKED_DELETE:
        return False, f"{key} cannot be deleted via API"
    dotenv_unset(key)
    return True, key
