"""Channels API — multi-account via openclaw channels CLI.

Endpoints:
- GET    /api/channels                            — list channels + accounts + field schemas
- GET    /api/channels/schema                     — supported channels + required fields
- POST   /api/channels/<channel>/accounts         — add new account (body: {account_id, ...fields})
- DELETE /api/channels/<channel>/accounts/<id>    — remove account
- (legacy) PUT/DELETE /api/channels/<channel>     — kept for backward compat

Note: Shared config with openclaw runtime means hot-reload picks up changes —
no systemd restart needed. Removing an account also prunes any binding that
references it (otherwise openclaw tries to start a non-existent provider and
crash-loops on getMe).
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.services import openclaw_channels_service, openclaw_config_service, systemd_service
from app.services.openclaw_channels_service import SUPPORTED_CHANNELS


def _prune_dangling_bindings(channel: str, account_id: str) -> int:
    """Remove bindings that target a now-deleted (channel, account)."""
    cfg = openclaw_config_service.read()
    bindings = cfg.get("bindings", []) or []
    kept = [
        b
        for b in bindings
        if not (
            (b.get("match", {}) or {}).get("channel") == channel
            and (b.get("match", {}) or {}).get("accountId") == account_id
        )
    ]
    removed = len(bindings) - len(kept)
    if removed:
        cfg["bindings"] = kept
        openclaw_config_service.write_atomic(cfg)
    return removed

channels_bp = Blueprint("channels", __name__, url_prefix="/api/channels")


@channels_bp.get("")
@require_bearer
def list_channels():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, "channels": openclaw_channels_service.list_channels()})


@channels_bp.get("/schema")
@require_bearer
def get_schema():  # type: ignore[no-untyped-def]
    return jsonify({"ok": True, "schema": openclaw_channels_service.supported_channels_meta()})


@channels_bp.post("/<channel>/accounts")
@require_bearer
def add_account(channel: str):  # type: ignore[no-untyped-def]
    if channel not in SUPPORTED_CHANNELS:
        return jsonify({"ok": False, "error": "Unknown channel"}), 404
    body = request.get_json(silent=True) or {}
    account_id = str(body.get("account_id") or body.get("accountId") or "").strip().lower()
    if not account_id:
        return jsonify({"ok": False, "error": "account_id required"}), 400
    fields = {k: v for k, v in body.items() if k not in {"account_id", "accountId"}}
    ok, msg = openclaw_channels_service.add_account(channel, account_id, fields)
    if ok:
        # Hot-reload reliably handles delete/update, but new-account spawn
        # sometimes silently fails — full restart guarantees the provider
        # actually starts polling.
        systemd_service.restart("openclaw")
    return jsonify({"ok": ok, "channel": channel, "account": account_id, "message": msg}), (
        201 if ok else 400
    )


@channels_bp.delete("/<channel>/accounts/<account_id>")
@require_bearer
def remove_account(channel: str, account_id: str):  # type: ignore[no-untyped-def]
    if channel not in SUPPORTED_CHANNELS:
        return jsonify({"ok": False, "error": "Unknown channel"}), 404
    ok, msg = openclaw_channels_service.remove_account(channel, account_id)
    bindings_removed = 0
    if ok:
        bindings_removed = _prune_dangling_bindings(channel, account_id)
    return jsonify(
        {
            "ok": ok,
            "channel": channel,
            "account": account_id,
            "message": msg,
            "bindings_removed": bindings_removed,
        }
    ), (200 if ok else 400)


# -- Legacy single-account endpoints (kept for backward compat) -------------


@channels_bp.put("/<channel>")
@require_bearer
def upsert_channel_legacy(channel: str):  # type: ignore[no-untyped-def]
    """Legacy single-account upsert — maps to 'default' account."""
    if channel not in SUPPORTED_CHANNELS:
        return jsonify({"ok": False, "error": "Unknown channel"}), 404
    body = request.get_json(silent=True) or {}
    # Service expects `token` (matches openclaw CLI --token) + `app_token` for
    # Slack secondary. Accept legacy `appToken` + `bot_token` aliases.
    fields = dict(body)
    if "appToken" in fields:
        fields["app_token"] = fields.pop("appToken")
    if "bot_token" in fields and "token" not in fields:
        fields["token"] = fields.pop("bot_token")
    ok, msg = openclaw_channels_service.add_account(channel, "default", fields)
    if ok:
        systemd_service.restart("openclaw")
    return jsonify({"ok": ok, "channel": channel, "message": msg}), (200 if ok else 400)


@channels_bp.delete("/<channel>")
@require_bearer
def delete_channel_legacy(channel: str):  # type: ignore[no-untyped-def]
    """Legacy single-account delete — removes the 'default' account."""
    if channel not in SUPPORTED_CHANNELS:
        return jsonify({"ok": False, "error": "Unknown channel"}), 404
    ok, msg = openclaw_channels_service.remove_account(channel, "default")
    if ok:
        _prune_dangling_bindings(channel, "default")
    return jsonify({"ok": ok, "channel": channel, "message": msg}), (200 if ok else 400)
