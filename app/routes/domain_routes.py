"""PUT /api/domain — change domain + reissue SSL."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.extensions import limiter
from app.services import domain_change_service

domain_bp = Blueprint("domain", __name__, url_prefix="/api")


@domain_bp.put("/domain")
@limiter.limit("3 per minute")
@require_bearer
def put_domain():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    if not domain:
        return jsonify({"ok": False, "error": "domain required"}), 400
    force_skip_dns = bool(body.get("forceDnsSkip", False))
    result = domain_change_service.change_domain(domain, force_skip_dns=force_skip_dns)
    return jsonify(result), (200 if result.get("ok") else 400)
