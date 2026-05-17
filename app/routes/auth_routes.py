"""User-credential management endpoints + public login.

Source endpoints (server.js ~250-410):
- POST /api/auth/login         — public; validates user/pass, returns gateway token
- POST /api/auth/create-user   — Bearer; hashes pwd; writes OPENCLAW_LOGIN_USER/PASS
- GET  /api/auth/user          — Bearer; reports config presence
- PUT  /api/auth/change-password — Bearer
- DELETE /api/auth/user        — Bearer
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import (
    record_auth_failure,
    require_bearer,
    scrypt_hash,
    scrypt_verify,
)
from app.utils.dotenv_atomic import dotenv_get, dotenv_set, dotenv_unset
from app.utils.ip_cidr_whitelist import get_client_ip

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/login")
def login():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    stored_user = dotenv_get("OPENCLAW_LOGIN_USER")
    stored_pass = dotenv_get("OPENCLAW_LOGIN_PASS")
    if not stored_user or not stored_pass:
        return jsonify({"ok": False, "error": "Login not configured"}), 503
    if username != stored_user or not scrypt_verify(stored_pass, password):
        record_auth_failure(get_client_ip(request))
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    gateway_token = dotenv_get("OPENCLAW_GATEWAY_TOKEN") or ""
    mgmt_api_key = dotenv_get("OPENCLAW_MGMT_API_KEY") or ""
    # User passed username+password — same trust boundary as pasting the raw
    # key. Returning mgmtApiKey lets the SPA bootstrap Bearer auth in one step.
    return jsonify(
        {"ok": True, "gatewayToken": gateway_token, "mgmtApiKey": mgmt_api_key}
    )


@auth_bp.post("/create-user")
@require_bearer
def create_user():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    dotenv_set("OPENCLAW_LOGIN_USER", username)
    dotenv_set("OPENCLAW_LOGIN_PASS", scrypt_hash(password))
    return jsonify({"ok": True, "username": username}), 201


@auth_bp.get("/user")
@require_bearer
def get_user():  # type: ignore[no-untyped-def]
    stored_user = dotenv_get("OPENCLAW_LOGIN_USER")
    return jsonify(
        {"ok": True, "configured": bool(stored_user), "username": stored_user or ""}
    )


@auth_bp.put("/change-password")
@require_bearer
def change_password():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    password = str(body.get("password", ""))
    if not password:
        return jsonify({"ok": False, "error": "password required"}), 400
    if not dotenv_get("OPENCLAW_LOGIN_USER"):
        return jsonify({"ok": False, "error": "No user configured"}), 404
    dotenv_set("OPENCLAW_LOGIN_PASS", scrypt_hash(password))
    return jsonify({"ok": True})


@auth_bp.delete("/user")
@require_bearer
def delete_user():  # type: ignore[no-untyped-def]
    dotenv_unset("OPENCLAW_LOGIN_USER")
    dotenv_unset("OPENCLAW_LOGIN_PASS")
    return jsonify({"ok": True})
