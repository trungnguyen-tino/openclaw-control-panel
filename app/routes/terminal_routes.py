"""GET /api/terminal/stream — Server-Sent Events of whitelisted command output."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.services.cli_whitelist import CliBlocked, parse
from app.services.terminal_stream_service import stream_command
from app.utils.dotenv_atomic import dotenv_get
from app.utils.secrets_mask import timing_safe_compare

terminal_bp = Blueprint("terminal", __name__, url_prefix="/api/terminal")


def _is_authed() -> bool:
    expected = dotenv_get("OPENCLAW_MGMT_API_KEY")
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return timing_safe_compare(header[7:].strip(), expected)
    qtoken = request.args.get("token", "").strip()
    if qtoken:
        return timing_safe_compare(qtoken, expected)
    return False


@terminal_bp.get("/stream")
def stream():  # type: ignore[no-untyped-def]
    if not _is_authed():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    command = request.args.get("command", "").strip()
    try:
        parts = parse(command)
    except CliBlocked as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(
        stream_with_context(stream_command(parts)),
        mimetype="text/event-stream",
        headers=headers,
    )
