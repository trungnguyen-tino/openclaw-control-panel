"""Read-through bridge to openclaw's session storage.

Lets the panel UI display openclaw conversations live (sessions + messages +
tail-as-they-arrive) without owning its own chat store. Source of truth stays
in openclaw — panel is just an alternative UI for the same data.

Endpoints (all require Bearer auth via @require_bearer):
- GET  /api/openclaw/sessions                     → list sessions
- GET  /api/openclaw/sessions/<sid>/messages      → parsed messages from jsonl
- GET  /api/openclaw/sessions/<sid>/stream        → SSE tail of jsonl appends
- POST /api/openclaw/sessions/<sid>/send          → forward a user turn
- DELETE /api/openclaw/sessions/<sid>             → soft-delete (archive jsonl + remove index entry)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterator

from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.auth import require_bearer
from app.extensions import limiter
from app.services.chat_service import one_shot

log = logging.getLogger("openclaw.openclaw_chat")

openclaw_chat_bp = Blueprint("openclaw_chat", __name__, url_prefix="/api/openclaw")

# All openclaw agent state lives under this directory. Multiple agents would
# extend the layout to /agents/{agentId}/sessions/... — we read main only.
_SESSIONS_DIR = Path("/opt/openclaw/.openclaw/agents/main/sessions")
_SESSIONS_INDEX = _SESSIONS_DIR / "sessions.json"
_TAIL_INTERVAL_S = 1.0
_TAIL_KEEPALIVE_S = 25.0


def _load_index() -> dict[str, Any]:
    if not _SESSIONS_INDEX.exists():
        return {}
    try:
        return json.loads(_SESSIONS_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("sessions.json parse failed: %s", exc)
        return {}


def _safe_session_path(sid: str) -> Path | None:
    """Resolve `<sid>.jsonl` inside _SESSIONS_DIR. Rejects path traversal."""
    if not sid or "/" in sid or ".." in sid:
        return None
    p = (_SESSIONS_DIR / f"{sid}.jsonl").resolve()
    try:
        p.relative_to(_SESSIONS_DIR.resolve())
    except ValueError:
        return None
    return p


@openclaw_chat_bp.get("/sessions")
@require_bearer
def list_sessions():  # type: ignore[no-untyped-def]
    idx = _load_index()
    out: list[dict[str, Any]] = []
    for key, sess in idx.items():
        sid = sess.get("sessionId")
        if not sid:
            continue
        jsonl = _safe_session_path(sid)
        has_messages = bool(jsonl and jsonl.exists() and jsonl.stat().st_size > 0)
        out.append(
            {
                "id": sid,
                "key": key,
                "updatedAt": sess.get("updatedAt"),
                "startedAt": sess.get("sessionStartedAt"),
                "status": sess.get("status"),
                "chatType": sess.get("chatType"),
                "endedAt": sess.get("endedAt"),
                "runtimeMs": sess.get("runtimeMs"),
                "hasMessages": has_messages,
            }
        )
    out.sort(key=lambda s: -(s.get("updatedAt") or 0))
    return jsonify({"ok": True, "sessions": out})


@openclaw_chat_bp.get("/sessions/<sid>/messages")
@require_bearer
def get_session_messages(sid: str):  # type: ignore[no-untyped-def]
    jsonl = _safe_session_path(sid)
    if jsonl is None:
        return jsonify({"ok": False, "error": "invalid session id"}), 400
    if not jsonl.exists():
        return jsonify({"ok": True, "exists": False, "messages": []})
    msgs: list[dict[str, Any]] = []
    try:
        with jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    msgs.append(json.loads(s))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "exists": True, "messages": msgs, "count": len(msgs)})


@openclaw_chat_bp.get("/sessions/<sid>/stream")
@require_bearer
def stream_session(sid: str):  # type: ignore[no-untyped-def]
    """SSE tail of {sid}.jsonl. Sends current content then appends as they arrive."""
    jsonl = _safe_session_path(sid)
    if jsonl is None:
        return jsonify({"ok": False, "error": "invalid session id"}), 400

    def gen() -> Iterator[str]:
        last_size = 0
        # Initial send of current content if file exists.
        if jsonl.exists():
            try:
                with jsonl.open("r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            yield f"data: {s}\n\n"
                last_size = jsonl.stat().st_size
            except OSError:
                pass
        last_keepalive = time.monotonic()
        # Tail loop. Polling is fine — JSONL is append-only, low frequency.
        while True:
            try:
                if jsonl.exists():
                    sz = jsonl.stat().st_size
                    if sz > last_size:
                        with jsonl.open("r", encoding="utf-8") as f:
                            f.seek(last_size)
                            for line in f:
                                s = line.strip()
                                if s:
                                    yield f"data: {s}\n\n"
                        last_size = sz
            except OSError:
                pass
            # Heartbeat so proxies (Caddy etc.) don't time out idle SSE.
            now = time.monotonic()
            if now - last_keepalive > _TAIL_KEEPALIVE_S:
                yield ": keepalive\n\n"
                last_keepalive = now
            time.sleep(_TAIL_INTERVAL_S)

    resp = Response(stream_with_context(gen()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"  # disable nginx-style buffering
    return resp


@openclaw_chat_bp.delete("/sessions/<sid>")
@limiter.limit("30 per minute")
@require_bearer
def delete_session(sid: str):  # type: ignore[no-untyped-def]
    """Soft-delete: rename jsonl to `<sid>.deleted-<ts>.jsonl` and drop the
    sessions.json entry. Keeps files on disk for recovery; daemon will spawn a
    fresh session on next user turn.
    """
    jsonl = _safe_session_path(sid)
    if jsonl is None:
        return jsonify({"ok": False, "error": "invalid session id"}), 400
    ts = int(time.time())
    archived: list[str] = []
    # Rename main + trajectory files if present.
    for suffix in (".jsonl", ".trajectory.jsonl", ".trajectory-path.json"):
        src = _SESSIONS_DIR / f"{sid}{suffix}"
        if src.exists():
            dst = _SESSIONS_DIR / f"{sid}.deleted-{ts}{suffix}"
            try:
                src.rename(dst)
                archived.append(dst.name)
            except OSError as exc:
                log.warning("rename %s failed: %s", src, exc)
    # Remove entry from sessions.json (key may be anything pointing at this sid).
    idx = _load_index()
    removed_keys = [k for k, v in idx.items() if v.get("sessionId") == sid]
    for k in removed_keys:
        idx.pop(k, None)
    try:
        _SESSIONS_INDEX.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    except OSError as exc:
        return jsonify({"ok": False, "error": f"index write failed: {exc}"}), 500
    return jsonify({"ok": True, "archived": archived, "removedKeys": removed_keys})


@openclaw_chat_bp.post("/sessions/<sid>/send")
@limiter.limit("30 per minute")
@require_bearer
def send_to_session(sid: str):  # type: ignore[no-untyped-def]
    """Forward a user message to openclaw.

    Uses the existing one-shot subprocess helper. openclaw's CLI runs against
    the configured agent — message + response both land in the active session
    on the openclaw side, which our SSE stream surfaces back to the panel.
    """
    # Validate sid only (we don't pin a specific session — openclaw routes
    # via its active agent). Kept in the URL so the panel UI can correlate
    # responses with the session it sent from.
    # Special sentinel "new": skip path validation; daemon spawns a fresh
    # session and the UI re-queries sessions.list to discover its id.
    if sid != "new" and _safe_session_path(sid) is None:
        return jsonify({"ok": False, "error": "invalid session id"}), 400
    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    model = body.get("model")
    result = one_shot(message, model=str(model) if model else None)
    return jsonify(result), (200 if result.get("ok") else 502)
