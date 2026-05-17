"""Channel → agent routing bindings.

Config is shared with the openclaw runtime (`.openclaw/openclaw.json`), so
hot-reload picks up bindings as soon as we write them — no CLI call needed.
We still write entries in openclaw's native schema (`type: "route"`).
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import openclaw_config_service

log = logging.getLogger("openclaw.bindings")


def _bindings(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return cfg.setdefault("bindings", [])


def _normalize_match(match: dict[str, Any]) -> dict[str, Any]:
    """Accept both `account` and `accountId` from callers; emit `accountId`."""
    ch = match.get("channel")
    acc = match.get("accountId") or match.get("account")
    out: dict[str, Any] = {}
    if ch:
        out["channel"] = ch
    if acc:
        out["accountId"] = acc
    return out


def _make_entry(agent_id: str, match: dict[str, Any]) -> dict[str, Any]:
    """Openclaw-native binding entry shape (strict — no extra fields)."""
    return {
        "type": "route",
        "agentId": agent_id,
        "match": _normalize_match(match),
    }


def list_bindings() -> list[dict[str, Any]]:
    return _bindings(openclaw_config_service.read())


def append_binding(agent_id: str, match: dict[str, Any]) -> tuple[bool, int]:
    if not match.get("channel"):
        return False, -1
    cfg = openclaw_config_service.read()
    arr = _bindings(cfg)
    arr.append(_make_entry(agent_id, match))
    openclaw_config_service.write_atomic(cfg)
    return True, len(arr) - 1


def update_binding(index: int, agent_id: str | None, match: dict[str, Any] | None) -> bool:
    cfg = openclaw_config_service.read()
    arr = _bindings(cfg)
    if index < 0 or index >= len(arr):
        return False
    entry = arr[index]
    final_agent = agent_id if agent_id is not None else entry.get("agentId", "")
    final_match = match if match is not None else entry.get("match", {})
    arr[index] = _make_entry(final_agent, final_match)
    openclaw_config_service.write_atomic(cfg)
    return True


def delete_binding(index: int) -> bool:
    cfg = openclaw_config_service.read()
    arr = _bindings(cfg)
    if index < 0 or index >= len(arr):
        return False
    del arr[index]
    openclaw_config_service.write_atomic(cfg)
    return True
