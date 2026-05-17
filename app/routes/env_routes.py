"""Environment-var endpoints — list/set/delete with locked-key protection."""

from __future__ import annotations

import re

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.services import env_service

env_bp = Blueprint("env", __name__, url_prefix="/api/env")

# Env-var keys: uppercase ASCII letters/digits/underscores; max 64 chars.
_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@env_bp.get("")
@require_bearer
def list_env():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, "env": env_service.list_masked()})


@env_bp.put("/<key>")
@require_bearer
def set_env(key: str):  # type: ignore[no-untyped-def]
    if not _KEY_RE.match(key):
        return jsonify({"ok": False, "error": "Invalid key (UPPER_SNAKE_CASE only)"}), 400
    body = request.get_json(silent=True) or {}
    value = body.get("value")
    if value is None:
        return jsonify({"ok": False, "error": "value required"}), 400
    ok, msg = env_service.set_value(key, str(value))
    return jsonify({"ok": ok, "key": key, "message": msg}), (200 if ok else 400)


@env_bp.delete("/<key>")
@require_bearer
def delete_env(key: str):  # type: ignore[no-untyped-def]
    if not _KEY_RE.match(key):
        return jsonify({"ok": False, "error": "Invalid key"}), 400
    ok, msg = env_service.delete_value(key)
    return jsonify({"ok": ok, "key": key, "message": msg}), (200 if ok else 400)
