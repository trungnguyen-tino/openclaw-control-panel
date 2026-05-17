"""ChatGPT Codex OAuth endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.extensions import limiter
from app.services import oauth_codex_service

oauth_bp = Blueprint("oauth_codex", __name__, url_prefix="/api/config/chatgpt-oauth")


@oauth_bp.post("/start")
@limiter.limit("10 per minute")
@require_bearer
def start():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    agent_id = str(body.get("agentId") or "default").strip()
    info = oauth_codex_service.start_session(agent_id=agent_id)
    return jsonify({"ok": True, **info})


@oauth_bp.post("/complete")
@limiter.limit("10 per minute")
@require_bearer
def complete():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    sid = str(body.get("sessionId", "")).strip()
    redirect_url = str(body.get("redirectUrl", "")).strip()
    model = body.get("model")
    switch = bool(body.get("switchProvider", False))
    if not sid or not redirect_url:
        return jsonify({"ok": False, "error": "sessionId and redirectUrl required"}), 400
    result = oauth_codex_service.complete_session(
        sid, redirect_url, model=model, switch_provider=switch
    )
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@oauth_bp.post("/refresh")
@require_bearer
def refresh():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    agent_id = str(body.get("agentId") or "default").strip()
    profile_key = body.get("profileKey")
    refreshed: list[dict[str, str]] = []
    if profile_key:
        ok = oauth_codex_service.refresh_profile(agent_id, str(profile_key))
        refreshed.append({"agentId": agent_id, "profileKey": profile_key, "ok": str(ok)})
    else:
        # Refresh every oauth profile for that agent.
        from app.services import auth_profiles_service

        for key, prof in auth_profiles_service.list_profiles(agent_id).items():
            if prof.get("type") == "oauth":
                ok = oauth_codex_service.refresh_profile(agent_id, key)
                refreshed.append({"agentId": agent_id, "profileKey": key, "ok": str(ok)})
    return jsonify({"ok": True, "refreshed": refreshed})
