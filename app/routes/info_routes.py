"""Read-only info endpoints: /api/info, /status, /version, /system, /logs, /domain."""

from __future__ import annotations

import socket

from flask import Blueprint, jsonify, request

from flask import Response, stream_with_context

from app.auth import require_bearer
from app.config import ALLOWED_SERVICES
from app.services import journalctl_service, systemd_service, system_info_service
from app.services.dns_check_service import resolve_a
from app.services.terminal_stream_service import stream_journalctl
from app.utils.dotenv_atomic import dotenv_get, dotenv_read
from app.utils.secrets_mask import sanitize_key, timing_safe_compare
from app.utils.subprocess_safe import run_cmd

info_bp = Blueprint("info", __name__, url_prefix="/api")


def _domain_from_env(env: dict[str, str]) -> str:
    domain = env.get("DOMAIN", "")
    if not domain:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "localhost"
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.split("://", 1)[1].rstrip("/")
    return domain.rstrip("/")


def _ssl_mode(env: dict[str, str]) -> str:
    tls = env.get("CADDY_TLS", "").strip()
    return "self-signed" if tls else "letsencrypt"


@info_bp.get("/info")
@require_bearer
def get_info():  # type: ignore[no-untyped-def]
    env = dotenv_read()
    domain = _domain_from_env(env)
    gateway_token = env.get("OPENCLAW_GATEWAY_TOKEN", "")
    mgmt_key = env.get("OPENCLAW_MGMT_API_KEY", "")
    resolved_ip = resolve_a(domain) if "." in domain else None
    status = "running" if systemd_service.is_active("openclaw") else "stopped"
    return jsonify(
        {
            "ok": True,
            "domain": domain,
            "ip": resolved_ip or "",
            "dashboardUrl": f"https://{domain}/",
            "gatewayToken": gateway_token,
            "mgmtApiKey": sanitize_key(mgmt_key),
            "status": status,
            "version": env.get("OPENCLAW_VERSION", "latest"),
            "ssl": _ssl_mode(env),
            "dnsStatus": "resolved" if resolved_ip else "unresolved",
        }
    )


@info_bp.get("/status")
@require_bearer
def get_status():  # type: ignore[no-untyped-def]
    openclaw_active = systemd_service.is_active("openclaw")
    caddy_active = systemd_service.is_active("caddy")
    started = systemd_service.started_at("openclaw")
    return jsonify(
        {
            "ok": True,
            "openclaw": {
                "status": "active" if openclaw_active else "inactive",
                "startedAt": started.isoformat() if started else None,
            },
            "caddy": {"status": "active" if caddy_active else "inactive"},
            "version": dotenv_read().get("OPENCLAW_VERSION", "latest"),
        }
    )


@info_bp.get("/version")
@require_bearer
def get_version():  # type: ignore[no-untyped-def]
    try:
        r = run_cmd(["/usr/bin/openclaw", "--version"], timeout=5)
        version = r.stdout.strip() or "unknown"
    except Exception:
        version = "unknown"
    return jsonify(
        {
            "ok": True,
            "version": dotenv_read().get("OPENCLAW_VERSION", "latest"),
            "clawVersion": version,
        }
    )


@info_bp.get("/system")
@require_bearer
def get_system():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, **system_info_service.gather()})


@info_bp.get("/logs")
@require_bearer
def get_logs():  # type: ignore[no-untyped-def]
    service = request.args.get("service", "openclaw").strip()
    try:
        lines = int(request.args.get("lines", "100"))
    except ValueError:
        return jsonify({"ok": False, "error": "lines must be integer"}), 400
    try:
        logs = journalctl_service.tail(service, lines=lines)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "service": service, "lines": len(logs), "logs": logs})


@info_bp.get("/logs/stream")
def logs_stream():  # type: ignore[no-untyped-def]
    """SSE-friendly live tail. Accepts Bearer OR `?token=` (EventSource can't set headers)."""
    expected = dotenv_get("OPENCLAW_MGMT_API_KEY")
    if not expected:
        return jsonify({"ok": False, "error": "Not configured"}), 503
    header = request.headers.get("Authorization", "")
    token: str | None = None
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        token = request.args.get("token", "").strip()
    if not token or not timing_safe_compare(token, expected):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    service = request.args.get("service", "openclaw").strip()
    if service not in ALLOWED_SERVICES:
        return jsonify({"ok": False, "error": "Service not in whitelist"}), 400
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(
        stream_with_context(stream_journalctl(service)),
        mimetype="text/event-stream",
        headers=headers,
    )


@info_bp.get("/domain")
@require_bearer
def get_domain():  # type: ignore[no-untyped-def]
    env = dotenv_read()
    domain = _domain_from_env(env)
    tls = env.get("CADDY_TLS", "").strip()
    return jsonify(
        {
            "ok": True,
            "domain": domain,
            "ip": resolve_a(domain),
            "ssl": _ssl_mode(env),
            "selfSignedSSL": bool(tls),
        }
    )
