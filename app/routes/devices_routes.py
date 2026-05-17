"""Device pairing endpoints — /api/devices, /api/devices/approve, /pair."""

from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request

from app.auth import require_bearer
from app.extensions import limiter
from app.services import devices_service, pairing_polling_service
from app.utils.dotenv_atomic import dotenv_get
from app.utils.secrets_mask import timing_safe_compare

devices_bp = Blueprint("devices", __name__)


@devices_bp.get("/api/devices")
@require_bearer
def list_devices():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, **devices_service.list_all()})


@devices_bp.post("/api/devices/approve/<device_id>")
@require_bearer
def approve_device(device_id: str):  # type: ignore[no-untyped-def]
    if not device_id or len(device_id) > 128:
        return jsonify({"ok": False, "error": "Invalid device id"}), 400
    result = devices_service.approve_one(device_id)
    if result is None:
        return jsonify({"ok": False, "error": "Device not pending"}), 404
    return jsonify({"ok": True, "device": result})


@devices_bp.get("/pair")
@limiter.limit("5 per minute")
def public_pair():  # type: ignore[no-untyped-def]
    """Public — validate gateway token, start 60s polling, 302 to gateway."""
    token = request.args.get("token", "").strip()
    expected = dotenv_get("OPENCLAW_GATEWAY_TOKEN")
    if not expected or not token or not timing_safe_compare(token, expected):
        return jsonify({"ok": False, "error": "Invalid token"}), 401
    pairing_polling_service.get_poller().activate()
    domain = dotenv_get("DOMAIN") or "localhost"
    if domain.startswith(("http://", "https://")):
        target = domain
    else:
        target = f"https://{domain}/"
    return redirect(target, code=302)
