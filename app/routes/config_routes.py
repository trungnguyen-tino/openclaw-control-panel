"""Provider + config endpoints: /api/config, /api/providers, /api/config/*."""

from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Blueprint, jsonify, request

from app import config as _cfg
from app.auth import require_bearer
from app.providers import key_tester, known_models
from app.services import openclaw_config_service, provider_service
from app.utils.dotenv_atomic import dotenv_read
from app.utils.secrets_mask import sanitize_key

config_bp = Blueprint("config", __name__, url_prefix="/api")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


@config_bp.get("/providers")
@require_bearer
def get_providers():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, "providers": provider_service.list_providers_response()})


@config_bp.get("/config")
@require_bearer
def get_config():  # type: ignore[no-untyped-def]
    cfg = openclaw_config_service.read()
    provider, model = openclaw_config_service.get_active_provider_model(cfg)
    env = dotenv_read()
    masked_keys: dict[str, str] = {}
    for pid, p in known_models.PROVIDERS.items():
        ek = p.get("env_key")
        if ek and env.get(ek):
            masked_keys[pid] = sanitize_key(env[ek])
    return jsonify(
        {
            "ok": True,
            "provider": provider,
            "model": model,
            "apiKeys": masked_keys,
            "agents": cfg.get("agents", {}).get("list", []),
            "bindings": cfg.get("bindings", []),
            "channels": cfg.get("channels", {}),
        }
    )


@config_bp.put("/config/provider")
@require_bearer
def put_provider():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    provider = str(body.get("provider", "")).strip()
    model = str(body.get("model", "")).strip()
    if not provider or not model:
        return jsonify({"ok": False, "error": "provider and model required"}), 400
    try:
        ok, msg = provider_service.switch_provider(provider, model)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    return jsonify({"ok": ok, "provider": provider, "model": model, "message": msg}), (
        200 if ok else 500
    )


@config_bp.put("/config/api-key")
@require_bearer
def put_api_key():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    provider = str(body.get("provider", "")).strip()
    api_key = str(body.get("apiKey", ""))
    agent_id = body.get("agentId")
    if not provider or not api_key:
        return jsonify({"ok": False, "error": "provider and apiKey required"}), 400
    ok, ref = provider_service.set_api_key(provider, api_key, agent_id=agent_id)
    return jsonify({"ok": ok, "provider": provider, "envKey": ref}), (200 if ok else 500)


@config_bp.delete("/config/api-key")
@require_bearer
def delete_api_key():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    provider = str(body.get("provider", "")).strip()
    agent_id = body.get("agentId")
    if not provider:
        return jsonify({"ok": False, "error": "provider required"}), 400
    ok, ref = provider_service.delete_api_key(provider, agent_id=agent_id)
    return jsonify({"ok": ok, "provider": provider, "envKey": ref})


@config_bp.post("/config/test-key")
@require_bearer
def post_test_key():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    provider = str(body.get("provider", "")).strip()
    api_key = str(body.get("apiKey", ""))
    if not provider:
        return jsonify({"ok": False, "error": "provider required"}), 400
    ok, msg = key_tester.test_key(provider, api_key)
    return jsonify({"ok": ok, "provider": provider, "message": msg})


# -- Custom provider lifecycle --------------------------------------------


def _custom_provider_path(provider_id: str) -> Path:
    return _cfg.PATHS.config_dir / f"{provider_id}.json"


def _validate_slug(slug: str) -> str | None:
    if not _SLUG_RE.match(slug):
        return "Invalid slug — use [a-z0-9-] up to 32 chars"
    if slug in known_models.PROVIDERS or slug == "openclaw":
        return "Slug collides with a built-in provider"
    return None


def _build_custom_template(
    provider_id: str, base_url: str, model_id: str, model_name: str, api: str
) -> dict:
    env_key = f"CUSTOM_{provider_id.upper().replace('-', '_')}_API_KEY"
    return {
        "agents": {
            "defaults": {
                "model": {"primary": openclaw_config_service.compose_primary(provider_id, model_id)},
                "maxConcurrent": 4,
                "subagents": {"maxConcurrent": 8},
            }
        },
        "models": {
            "mode": "merge",
            "providers": {
                provider_id: {
                    "baseUrl": base_url,
                    "apiKey": f"${{{env_key}}}",
                    "api": api,
                    "models": [{"id": model_id, "name": model_name}],
                }
            },
        },
        "gateway": {
            "mode": "local",
            "bind": "lan",
            "auth": {"token": "${OPENCLAW_GATEWAY_TOKEN}"},
            "trustedProxies": [
                "127.0.0.1",
                "::1",
                "172.16.0.0/12",
                "10.0.0.0/8",
                "192.168.0.0/16",
            ],
            "controlUi": {
                "enabled": True,
                "allowInsecureAuth": True,
                "dangerouslyAllowHostHeaderOriginFallback": True,
                "dangerouslyDisableDeviceAuth": False,
            },
        },
        "browser": {"headless": True, "defaultProfile": "openclaw", "noSandbox": True},
    }


@config_bp.post("/config/custom-provider")
@require_bearer
def post_custom_provider():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or body.get("provider", "")).strip().lower()
    err = _validate_slug(pid) if pid else "id required"
    if err:
        return jsonify({"ok": False, "error": err}), 400
    base_url = str(body.get("baseUrl", "")).strip()
    if not base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return jsonify({"ok": False, "error": "baseUrl must be HTTPS"}), 400
    model_id = str(body.get("model", "")).strip()
    model_name = str(body.get("modelName", model_id)).strip()
    api_type = str(body.get("api", "openai-completions")).strip()
    api_key = str(body.get("apiKey", "")).strip()
    if not model_id:
        return jsonify({"ok": False, "error": "model required"}), 400
    tpl = _build_custom_template(pid, base_url, model_id, model_name, api_type)
    path = _custom_provider_path(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tpl, indent=2), encoding="utf-8")
    if api_key:
        provider_service.set_api_key(pid, api_key)
    return jsonify({"ok": True, "id": pid, "path": str(path)}), 201


@config_bp.get("/config/custom-providers")
@require_bearer
def list_custom_providers():  # type: ignore[no-untyped-def]
    custom_dir = _cfg.PATHS.config_dir
    if not custom_dir.is_dir():
        return jsonify({"ok": True, "providers": []})
    builtin = set(known_models.PROVIDERS.keys())
    out = []
    for f in sorted(custom_dir.glob("*.json")):
        if f.stem in builtin or f.stem == "openclaw":
            continue
        try:
            tpl = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001, S112 — skip malformed custom-provider files; not fatal for the listing
            continue
        provider_cfg = tpl.get("models", {}).get("providers", {}).get(f.stem, {})
        out.append(
            {
                "id": f.stem,
                "baseUrl": provider_cfg.get("baseUrl"),
                "api": provider_cfg.get("api"),
                "models": provider_cfg.get("models", []),
            }
        )
    return jsonify({"ok": True, "providers": out})


@config_bp.put("/config/custom-provider/<provider>")
@require_bearer
def put_custom_provider(provider: str):  # type: ignore[no-untyped-def]
    err = _validate_slug(provider)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    path = _custom_provider_path(provider)
    if not path.is_file():
        return jsonify({"ok": False, "error": "Not found"}), 404
    body = request.get_json(silent=True) or {}
    tpl = json.loads(path.read_text(encoding="utf-8"))
    pcfg = tpl.setdefault("models", {}).setdefault("providers", {}).setdefault(provider, {})
    if "baseUrl" in body:
        pcfg["baseUrl"] = str(body["baseUrl"]).strip()
    if "api" in body:
        pcfg["api"] = str(body["api"]).strip()
    if "model" in body:
        pcfg["models"] = [{"id": body["model"], "name": body.get("modelName", body["model"])}]
        tpl.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
        tpl["agents"]["defaults"]["model"]["primary"] = openclaw_config_service.compose_primary(provider, body["model"])
    path.write_text(json.dumps(tpl, indent=2), encoding="utf-8")
    if body.get("apiKey"):
        provider_service.set_api_key(provider, str(body["apiKey"]))
    return jsonify({"ok": True, "id": provider})


@config_bp.delete("/config/custom-provider/<provider>")
@require_bearer
def delete_custom_provider(provider: str):  # type: ignore[no-untyped-def]
    err = _validate_slug(provider)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    path = _custom_provider_path(provider)
    if not path.is_file():
        return jsonify({"ok": False, "error": "Not found"}), 404
    path.unlink()
    # If this provider was active, fall back to anthropic.
    current = openclaw_config_service.read()
    active_provider, _ = openclaw_config_service.get_active_provider_model(current)
    if active_provider == provider:
        provider_service.switch_provider("anthropic", "claude-sonnet-4-20250514")
    provider_service.delete_api_key(provider)
    return jsonify({"ok": True, "id": provider, "deleted": True})
