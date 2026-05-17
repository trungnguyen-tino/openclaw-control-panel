"""Multi-agent CRUD.

Config is shared with the openclaw runtime (`.openclaw/openclaw.json`), so
hot-reload picks up new/removed agents as soon as we write them. We also
provision the workspace/agent dirs that openclaw expects to find on disk.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from app import config as _cfg
from app.services import auth_profiles_service, openclaw_config_service
from app.utils.secrets_mask import sanitize_key

log = logging.getLogger("openclaw.agents")


def _agents_list(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return cfg.setdefault("agents", {}).setdefault("list", [])


def _ensure_dirs(agent_id: str) -> None:
    base = _cfg.PATHS.agents_dir / agent_id
    (base / "agent").mkdir(parents=True, exist_ok=True)
    (base / "workspace").mkdir(parents=True, exist_ok=True)
    (base / ".openclaw").mkdir(parents=True, exist_ok=True)


def list_agents() -> list[dict[str, Any]]:
    cfg = openclaw_config_service.read()
    out: list[dict[str, Any]] = []
    for a in _agents_list(cfg):
        aid = a.get("id", "")
        profiles = auth_profiles_service.list_profiles(aid) if aid else {}
        out.append(
            {
                "id": aid,
                "name": a.get("name", aid),
                "default": bool(a.get("default")),
                "model": a.get("model"),
                "hasAuthProfiles": bool(profiles),
                "apiKeyCount": sum(
                    1 for p in profiles.values() if p.get("type") == "api_key"
                ),
            }
        )
    return out


def get_agent(agent_id: str) -> dict[str, Any] | None:
    cfg = openclaw_config_service.read()
    for a in _agents_list(cfg):
        if a.get("id") == agent_id:
            profiles = auth_profiles_service.list_profiles(agent_id)
            masked: dict[str, str] = {}
            for key, prof in profiles.items():
                if prof.get("type") == "api_key" and prof.get("key"):
                    masked[key] = sanitize_key(prof["key"])
            return {**a, "apiKeysMasked": masked}
    return None


def create_agent(
    agent_id: str,
    name: str | None = None,
    model: str | None = None,
    default: bool = False,
) -> tuple[bool, str]:
    cfg = openclaw_config_service.read()
    lst = _agents_list(cfg)
    if any(a.get("id") == agent_id for a in lst):
        return False, "Agent already exists"
    _ensure_dirs(agent_id)
    auth_profiles_service.write_atomic(agent_id, {"profiles": {}})
    entry: dict[str, Any] = {
        "id": agent_id,
        "name": name or agent_id,
        "workspace": str(_cfg.PATHS.agents_dir / agent_id / "workspace"),
        "agentDir": str(_cfg.PATHS.agents_dir / agent_id / "agent"),
    }
    if model:
        entry["model"] = model
    if default or not lst:
        for a in lst:
            a["default"] = False
        entry["default"] = True
    lst.append(entry)
    openclaw_config_service.write_atomic(cfg)
    return True, agent_id


def update_agent(agent_id: str, **fields: Any) -> tuple[bool, str]:
    cfg = openclaw_config_service.read()
    for a in _agents_list(cfg):
        if a.get("id") == agent_id:
            for k, v in fields.items():
                if k in {"name", "model", "workspace", "agentDir"} and v is not None:
                    a[k] = v
            openclaw_config_service.write_atomic(cfg)
            return True, agent_id
    return False, "Agent not found"


def delete_agent(agent_id: str, delete_data: bool = False) -> tuple[bool, str]:
    cfg = openclaw_config_service.read()
    lst = _agents_list(cfg)
    if len(lst) <= 1:
        return False, "Cannot delete the last agent"
    target = next((a for a in lst if a.get("id") == agent_id), None)
    if not target:
        return False, "Agent not found"
    if target.get("default"):
        return False, "Cannot delete the default agent — set another as default first"
    cfg["agents"]["list"] = [a for a in lst if a.get("id") != agent_id]
    openclaw_config_service.write_atomic(cfg)
    if delete_data:
        agent_dir = _cfg.PATHS.agents_dir / agent_id
        if agent_dir.is_dir():
            shutil.rmtree(agent_dir, ignore_errors=True)
    return True, agent_id


def set_default(agent_id: str) -> tuple[bool, str]:
    cfg = openclaw_config_service.read()
    lst = _agents_list(cfg)
    if not any(a.get("id") == agent_id for a in lst):
        return False, "Agent not found"
    for a in lst:
        a["default"] = a.get("id") == agent_id
    openclaw_config_service.write_atomic(cfg)
    return True, agent_id


def _agent_exists(agent_id: str) -> bool:
    cfg = openclaw_config_service.read()
    return any(a.get("id") == agent_id for a in _agents_list(cfg))


def set_agent_api_key(agent_id: str, provider: str, api_key: str) -> tuple[bool, str]:
    if not _agent_exists(agent_id):
        return False, f"Agent '{agent_id}' not found — create it first"
    auth_profiles_service.set_api_key(agent_id, provider, api_key)
    return True, f"agents/{agent_id}"


def delete_agent_api_key(agent_id: str, provider: str) -> tuple[bool, str]:
    if not _agent_exists(agent_id):
        return False, f"Agent '{agent_id}' not found"
    auth_profiles_service.delete_api_key(agent_id, provider)
    return True, f"agents/{agent_id}"
