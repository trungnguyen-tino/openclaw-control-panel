"""Channel→agent routing binding endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.services import bindings_service

bindings_bp = Blueprint("bindings", __name__, url_prefix="/api/bindings")


@bindings_bp.get("")
@require_bearer
def list_bindings():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, "bindings": bindings_service.list_bindings()})


@bindings_bp.post("")
@require_bearer
def create_binding():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    agent_id = str(body.get("agentId", "")).strip()
    match = body.get("match") or {}
    if not agent_id or not isinstance(match, dict) or not match.get("channel"):
        return jsonify({"ok": False, "error": "agentId and match.channel required"}), 400
    ok, idx = bindings_service.append_binding(agent_id, match)
    return jsonify({"ok": ok, "index": idx}), (201 if ok else 400)


@bindings_bp.put("/<int:index>")
@require_bearer
def update_binding(index: int):  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    ok = bindings_service.update_binding(
        index,
        agent_id=body.get("agentId"),
        match=body.get("match"),
    )
    return jsonify({"ok": ok, "index": index}), (200 if ok else 404)


@bindings_bp.delete("/<int:index>")
@require_bearer
def delete_binding(index: int):  # type: ignore[no-untyped-def]
    ok = bindings_service.delete_binding(index)
    return jsonify({"ok": ok, "index": index}), (200 if ok else 404)
