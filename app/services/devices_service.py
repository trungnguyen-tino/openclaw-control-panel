"""Device pairing — read/write `pending.json` + `paired.json`."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from app import config as _cfg
from app.utils.secrets_mask import sanitize_key

log = logging.getLogger("openclaw.devices")

_FILE_MODE = 0o600
_WRITE_LOCK = threading.Lock()


def _pending_path() -> Path:
    return _cfg.PATHS.devices_pending


def _paired_path() -> Path:
    return _cfg.PATHS.devices_paired


def _read_json(p: Path) -> dict[str, Any]:
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        log.warning("devices file malformed at %s — resetting", p)
        return {}


def _write_json_atomic(data: dict[str, Any], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp = tempfile.mkstemp(prefix=".devices.", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, _FILE_MODE)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise


def _gen_role_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def read_pending() -> dict[str, Any]:
    return _read_json(_pending_path())


def read_paired() -> dict[str, Any]:
    return _read_json(_paired_path())


def approve_one(device_id: str) -> dict[str, Any] | None:
    pending = read_pending()
    if device_id not in pending:
        return None
    paired = read_paired()
    src = pending.pop(device_id)
    roles = src.get("roles") or ["operator"]
    now_ms = int(time.time() * 1000)
    tokens = {
        role: {
            "token": _gen_role_token(),
            "role": role,
            "scopes": src.get("scopes", []),
            "createdAtMs": now_ms,
        }
        for role in roles
    }
    paired[device_id] = {
        "deviceId": device_id,
        "model": src.get("model"),
        "osVersion": src.get("osVersion"),
        "appVersion": src.get("appVersion"),
        "tokens": tokens,
        "approvedScopes": src.get("scopes", []),
        "createdAtMs": src.get("createdAtMs", now_ms),
        "approvedAtMs": now_ms,
    }
    _write_json_atomic(pending, _pending_path())
    _write_json_atomic(paired, _paired_path())
    log.info("[Devices] approved deviceId=%s", device_id)
    return paired[device_id]


def approve_all_pending() -> int:
    pending = read_pending()
    n = 0
    for device_id in list(pending.keys()):
        if approve_one(device_id) is not None:
            n += 1
    if n:
        log.info("[Devices] auto-approved %d devices", n)
    return n


def list_all() -> dict[str, Any]:
    pending = read_pending()
    paired = read_paired()
    return {
        "pending": [{"deviceId": k, **v} for k, v in pending.items()],
        "paired": [_mask_paired(v) for v in paired.values()],
    }


def _mask_paired(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    masked_tokens: dict[str, Any] = {}
    for role, t in entry.get("tokens", {}).items():
        masked_tokens[role] = {**t, "token": sanitize_key(t.get("token", ""))}
    out["tokens"] = masked_tokens
    return out
