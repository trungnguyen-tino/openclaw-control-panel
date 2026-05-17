"""Per-agent `auth-profiles.json` reader/writer.

Schema (source line ~731-760):
```
{
  "profiles": {
    "<provider>:manual": {"type":"api_key","provider":"<id>","key":"sk-..."},
    "openai-codex:<email>": {"type":"oauth","provider":"openai-codex",
                              "access":"...","refresh":"...","expires":<ms>,"accountId":"..."}
  }
}
```

Defensive read: malformed JSON / missing `profiles` → returns `{profiles:{}}` and
logs a warning. The Node source crashes silently on bad files; we degrade gracefully.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from app import config as _cfg

log = logging.getLogger("openclaw.auth_profiles")

AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FILE_MODE = 0o600
_WRITE_LOCK = threading.Lock()


def _path(agent_id: str) -> Path:
    if not AGENT_ID_RE.match(agent_id):
        raise ValueError(f"Invalid agent id: {agent_id!r}")
    return _cfg.PATHS.agents_dir / agent_id / "agent" / "auth-profiles.json"


def read(agent_id: str) -> dict[str, Any]:
    p = _path(agent_id)
    if not p.is_file():
        return {"profiles": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("auth-profiles.json malformed for agent=%s — resetting", agent_id)
        return {"profiles": {}}
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        return {"profiles": {}}
    return data


def write_atomic(agent_id: str, data: dict[str, Any]) -> None:
    p = _path(agent_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp = tempfile.mkstemp(prefix=".auth-profiles.", dir=str(p.parent))
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


def set_api_key(agent_id: str, provider: str, api_key: str) -> None:
    data = read(agent_id)
    profiles = data.setdefault("profiles", {})
    profiles[f"{provider}:manual"] = {
        "type": "api_key",
        "provider": provider,
        "key": api_key,
    }
    write_atomic(agent_id, data)


def delete_api_key(agent_id: str, provider: str) -> None:
    data = read(agent_id)
    data.get("profiles", {}).pop(f"{provider}:manual", None)
    write_atomic(agent_id, data)


def set_oauth_profile(agent_id: str, profile_key: str, payload: dict[str, Any]) -> None:
    """Used by phase-06 OAuth complete + refresh."""
    data = read(agent_id)
    data.setdefault("profiles", {})[profile_key] = payload
    write_atomic(agent_id, data)


def delete_oauth_profile(agent_id: str, profile_key: str) -> None:
    data = read(agent_id)
    data.get("profiles", {}).pop(profile_key, None)
    write_atomic(agent_id, data)


def list_profiles(agent_id: str) -> dict[str, dict[str, Any]]:
    return read(agent_id).get("profiles", {})
