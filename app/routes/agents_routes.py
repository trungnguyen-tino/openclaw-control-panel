"""Multi-agent endpoints (8 routes)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.services import agent_service, auth_profiles_service
from app.services.auth_profiles_service import AGENT_ID_RE
from app.utils.secrets_mask import sanitize_key

agents_bp = Blueprint("agents", __name__, url_prefix="/api/agents")


@agents_bp.get("")
@require_bearer
def list_agents_route():  # type: ignore[no-untyped-def]
    agents = agent_service.list_agents()
    return jsonify({"ok": True, "agents": agents, "count": len(agents)})


@agents_bp.post("")
@require_bearer
def create_agent_route():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    agent_id = str(body.get("id", "")).strip()
    if not agent_id or not AGENT_ID_RE.match(agent_id):
        return (
            jsonify({"ok": False, "error": "id required, [a-z0-9-], max 64 chars"}),
            400,
        )
    ok, msg = agent_service.create_agent(
        agent_id,
        name=body.get("name"),
        model=body.get("model"),
        default=bool(body.get("default", False)),
    )
    return jsonify({"ok": ok, "id": agent_id, "message": msg}), (201 if ok else 409)


@agents_bp.get("/<agent_id>")
@require_bearer
def get_agent_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    detail = agent_service.get_agent(agent_id)
    if not detail:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "agent": detail})


@agents_bp.put("/<agent_id>")
@require_bearer
def update_agent_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    body = request.get_json(silent=True) or {}
    ok, msg = agent_service.update_agent(
        agent_id,
        name=body.get("name"),
        model=body.get("model"),
        workspace=body.get("workspace"),
        agentDir=body.get("agentDir"),
    )
    return jsonify({"ok": ok, "id": agent_id, "message": msg}), (200 if ok else 404)


@agents_bp.delete("/<agent_id>")
@require_bearer
def delete_agent_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    body = request.get_json(silent=True) or {}
    ok, msg = agent_service.delete_agent(agent_id, delete_data=bool(body.get("deleteData")))
    return jsonify({"ok": ok, "id": agent_id, "message": msg}), (200 if ok else 400)


@agents_bp.put("/<agent_id>/default")
@require_bearer
def set_default_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    ok, msg = agent_service.set_default(agent_id)
    return jsonify({"ok": ok, "default": agent_id, "message": msg}), (
        200 if ok else 404
    )


@agents_bp.get("/<agent_id>/api-key")
@require_bearer
def list_agent_keys_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    profiles = auth_profiles_service.list_profiles(agent_id)
    masked: dict[str, dict[str, str]] = {}
    for key, prof in profiles.items():
        if prof.get("type") == "api_key":
            masked[key] = {
                "provider": prof.get("provider", ""),
                "key": sanitize_key(prof.get("key", "")),
            }
        elif prof.get("type") == "oauth":
            masked[key] = {
                "provider": prof.get("provider", ""),
                "accountId": prof.get("accountId", ""),
                "type": "oauth",
            }
    return jsonify({"ok": True, "agentId": agent_id, "profiles": masked})


@agents_bp.put("/<agent_id>/api-key")
@require_bearer
def put_agent_key_route(agent_id: str):  # type: ignore[no-untyped-def]
    if not AGENT_ID_RE.match(agent_id):
        return jsonify({"ok": False, "error": "Invalid id"}), 400
    body = request.get_json(silent=True) or {}
    provider = str(body.get("provider", "")).strip()
    api_key = str(body.get("apiKey", ""))
    if not provider or not api_key:
        return jsonify({"ok": False, "error": "provider and apiKey required"}), 400
    ok, ref = agent_service.set_agent_api_key(agent_id, provider, api_key)
    return jsonify(
        {"ok": ok, "agentId": agent_id, "provider": provider, "ref": ref}
    ), (200 if ok else 404)
