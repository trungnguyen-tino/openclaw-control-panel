"""Authentication primitives: scrypt password, Bearer decorator, IP rate-limit.

Source-compatibility contract:
- scrypt params: N=16384, r=8, p=1, dklen=64 (matches Node `crypto.scryptSync`).
- Stored format: `<salthex>:<hashhex>` — verbatim from source server.js:65-70.
- Rate-limit thresholds: 10 failures / 15 min per IP (server.js:81-83).
- Whitelisted CIDRs bypass the rate limiter (but NOT the auth check itself).
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import jsonify, request

from app.config import BLOCK_DURATION_MS, MAX_AUTH_FAILURES
from app.utils.dotenv_atomic import dotenv_get
from app.utils.ip_cidr_whitelist import get_client_ip, is_whitelisted_ip
from app.utils.secrets_mask import timing_safe_compare

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


def scrypt_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"{salt.hex()}:{derived.hex()}"


def scrypt_verify(stored: str, password: str) -> bool:
    if not stored or ":" not in stored:
        return False
    salthex, hashhex = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salthex)
    except ValueError:
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return timing_safe_compare(derived.hex(), hashhex)


# ---------------------------------------------------------------------------
# In-memory rate limit (matches source — resets on process restart).
# ---------------------------------------------------------------------------
_FAILED: dict[str, dict[str, float]] = {}
_FAILED_LOCK = threading.Lock()


def _now_ms() -> float:
    return time.time() * 1000.0


def record_auth_failure(ip: str) -> None:
    if is_whitelisted_ip(ip):
        return
    with _FAILED_LOCK:
        entry = _FAILED.setdefault(ip, {"count": 0.0, "blocked_until": 0.0})
        entry["count"] += 1
        if entry["count"] >= MAX_AUTH_FAILURES:
            entry["blocked_until"] = _now_ms() + BLOCK_DURATION_MS


def clear_auth_failures(ip: str) -> None:
    with _FAILED_LOCK:
        _FAILED.pop(ip, None)


def is_ip_blocked(ip: str) -> tuple[bool, float]:
    """Return (blocked, retry_after_seconds)."""
    if is_whitelisted_ip(ip):
        return False, 0.0
    with _FAILED_LOCK:
        entry = _FAILED.get(ip)
        if not entry:
            return False, 0.0
        if entry["blocked_until"] <= _now_ms():
            if entry["blocked_until"] != 0:
                # Block window expired — reset counter.
                _FAILED.pop(ip, None)
            return False, 0.0
        return True, (entry["blocked_until"] - _now_ms()) / 1000.0


def _extract_bearer(header_value: str | None) -> str | None:
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _read_mgmt_key() -> str | None:
    return dotenv_get("OPENCLAW_MGMT_API_KEY")


def require_bearer(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Protect a route with Bearer + per-IP rate limit.

    Behavior:
    - Missing/malformed header → 401 + IP failure recorded.
    - Wrong key → 401 + IP failure recorded.
    - 10th consecutive failure → next request gets 429 with Retry-After.
    - Correct key → clears the IP's failure counter, proceeds.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ip = get_client_ip(request)
        blocked, retry_after = is_ip_blocked(ip)
        if blocked:
            resp = jsonify(
                {
                    "ok": False,
                    "error": "Too many failed attempts. Blocked for 15 minutes.",
                }
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(int(retry_after))
            return resp

        token = _extract_bearer(request.headers.get("Authorization"))
        if not token:
            # SSE / EventSource cannot send Authorization headers — accept
            # `?auth=` as a fallback for streaming endpoints only.
            token = request.args.get("auth") or None
        expected = _read_mgmt_key()
        if not expected:
            return (
                jsonify({"ok": False, "error": "Management API key not configured"}),
                503,
            )
        if not token or not timing_safe_compare(token, expected):
            record_auth_failure(ip)
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        clear_auth_failures(ip)
        return fn(*args, **kwargs)

    return wrapper
