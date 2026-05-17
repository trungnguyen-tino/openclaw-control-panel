"""High-level provider operations: switch provider, manage API keys."""

from __future__ import annotations

import json
from typing import Any

from app import config as _cfg
from app.providers import known_models, template_loader
from app.services import openclaw_config_service, systemd_service
from app.utils.dotenv_atomic import dotenv_read, dotenv_set, dotenv_unset
from app.utils.secrets_mask import sanitize_key


def switch_provider(provider: str, model: str) -> tuple[bool, str]:
    """Load template, merge with current, write atomically, restart openclaw.

    Rolls back `openclaw.json` to the pre-switch snapshot if restart fails so
    the gateway never gets stuck on a broken config.
    """
    if provider in known_models.PROVIDERS:
        template = template_loader.load_template(provider)
    else:
        custom_path = _cfg.PATHS.config_dir / f"{provider}.json"
        if not custom_path.is_file():
            return False, f"Unknown provider '{provider}'"
        template = json.loads(custom_path.read_text(encoding="utf-8"))
    snapshot = openclaw_config_service.read()  # for rollback
    merged = openclaw_config_service.merge_template(snapshot, template, provider, model)
    openclaw_config_service.write_atomic(merged)
    ok, msg = systemd_service.restart("openclaw")
    if not ok:
        # Restart failed — restore pre-switch config so retries don't hit the
        # broken file. Best-effort second restart on the restored config.
        if snapshot:
            openclaw_config_service.write_atomic(snapshot)
        systemd_service.restart("openclaw")
        return False, f"restart failed, rolled back: {msg}"
    return ok, msg


def set_api_key(provider: str, api_key: str, agent_id: str | None = None) -> tuple[bool, str]:
    """Persist API key.

    - No `agent_id` → write to `.env[<PROVIDER>_API_KEY]` (main agent).
    - With `agent_id` → delegate to agent_service (phase 05).
    """
    if agent_id:
        from app.services import agent_service  # late import to avoid cycle

        return agent_service.set_agent_api_key(agent_id, provider, api_key)
    env_key = known_models.env_key_for(provider)
    if not env_key:
        # Custom provider — derive `CUSTOM_<UPPER>_API_KEY`
        env_key = f"CUSTOM_{provider.upper().replace('-', '_')}_API_KEY"
    dotenv_set(env_key, api_key)
    return True, env_key


def delete_api_key(provider: str, agent_id: str | None = None) -> tuple[bool, str]:
    if agent_id:
        from app.services import agent_service

        return agent_service.delete_agent_api_key(agent_id, provider)
    env_key = known_models.env_key_for(provider) or f"CUSTOM_{provider.upper().replace('-', '_')}_API_KEY"
    dotenv_unset(env_key)
    return True, env_key


def _oauth_profile_for(provider_id: str) -> dict[str, Any] | None:
    """Look up an OAuth profile for `provider_id` on the default agent.

    auth_profiles.json keys look like `<provider>:<email>` — match by prefix.
    """
    from app.services import auth_profiles_service, openclaw_config_service

    cfg = openclaw_config_service.read()
    agent_list = (cfg.get("agents", {}) or {}).get("list", []) or []
    default_agent = next((a.get("id") for a in agent_list if a.get("default")), None) \
        or (agent_list[0].get("id") if agent_list else "main")
    profiles = auth_profiles_service.list_profiles(default_agent) or {}
    for key, prof in profiles.items():
        if isinstance(prof, dict) and prof.get("provider") == provider_id and prof.get("type") == "oauth":
            return prof
    # Fallback to scanning legacy "default" agent (panels created before agents.list init).
    if default_agent != "default":
        legacy = auth_profiles_service.list_profiles("default") or {}
        for key, prof in legacy.items():
            if isinstance(prof, dict) and prof.get("provider") == provider_id and prof.get("type") == "oauth":
                return prof
    return None


def list_providers_response() -> list[dict[str, Any]]:
    """Output for `GET /api/providers` — built-ins + customs."""
    out: list[dict[str, Any]] = []
    env_data = dotenv_read()
    for pid, p in known_models.PROVIDERS.items():
        env_key = p.get("env_key")
        api_key_set = bool(env_key and env_data.get(env_key))
        oauth_profile = _oauth_profile_for(pid) if p.get("oauth_only") else None
        out.append(
            {
                "id": pid,
                "name": p.get("name", pid),
                "envKey": env_key,
                "oauthOnly": bool(p.get("oauth_only")),
                "models": list(p.get("known_models", [])),
                "knownModels": list(p.get("known_models", [])),
                "apiKey": sanitize_key(env_data.get(env_key, "")) if env_key else None,
                "configured": api_key_set or bool(oauth_profile),
                "email": oauth_profile.get("email") if oauth_profile else None,
            }
        )
    # Custom providers
    custom_dir = _cfg.PATHS.config_dir
    if custom_dir.is_dir():
        builtin = set(known_models.PROVIDERS.keys())
        for f in sorted(custom_dir.glob("*.json")):
            if f.stem in builtin or f.stem == "openclaw":
                continue
            try:
                tpl = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            env_key = f"CUSTOM_{f.stem.upper().replace('-', '_')}_API_KEY"
            out.append(
                {
                    "id": f.stem,
                    "name": f.stem,
                    "envKey": env_key,
                    "oauthOnly": False,
                    "custom": True,
                    "models": list(
                        tpl.get("models", {})
                        .get("providers", {})
                        .get(f.stem, {})
                        .get("models", [])
                    ),
                    "knownModels": [],
                    "apiKey": sanitize_key(env_data.get(env_key, "")),
                    "configured": bool(env_data.get(env_key)),
                }
            )
    return out
