"""POST /api/cli — execute shell commands and return output.

Two modes:
- `raw=false` (default): whitelisted prefix + no shell metacharacters. Safe.
- `raw=true`: full shell via `bash -lc`. Requires Bearer auth (already enforced).
  Equivalent privilege to SSH root login since the management service runs as
  root. Use for ad-hoc admin tasks (pairing approve, log inspect, file edit).
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth import require_bearer
from app.extensions import limiter
from app.services.cli_whitelist import CliBlocked, parse
from app.utils.subprocess_safe import run_cmd

cli_bp = Blueprint("cli", __name__, url_prefix="/api")

_MAX_OUTPUT_BYTES = 1_000_000  # 1MB safety cap on response payload
_RAW_TIMEOUT_S = 60.0


@cli_bp.post("/cli")
@limiter.limit("20 per minute")
@require_bearer
def post_cli():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    command = str(body.get("command", "")).strip()
    raw = bool(body.get("raw", False))
    if not command:
        return jsonify({"ok": False, "error": "command required"}), 400

    if raw:
        args = ["bash", "-lc", command]
        display_cmd = command
        timeout = _RAW_TIMEOUT_S
    else:
        try:
            args = parse(command)
        except CliBlocked as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        display_cmd = command
        timeout = 30.0

    try:
        r = run_cmd(args, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e), "cmd": display_cmd}), 500
    stdout = (r.stdout or "")[:_MAX_OUTPUT_BYTES]
    stderr = (r.stderr or "")[:_MAX_OUTPUT_BYTES]
    return jsonify(
        {
            "ok": r.returncode == 0,
            "exitCode": r.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "cmd": display_cmd,
            "raw": raw,
        }
    )
