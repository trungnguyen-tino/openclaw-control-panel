"""In-panel chat — wraps `openclaw capability model run` for a one-shot turn.

Subprocess approach (vs. direct WS gateway connection) keeps the implementation
trivial: openclaw CLI already speaks our config + handles provider routing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.openclaw_config_service import get_active_provider_model
from app.utils.dotenv_atomic import dotenv_get
from app.utils.subprocess_safe import run_cmd

log = logging.getLogger("openclaw.chat")

_OPENCLAW_BIN = "/usr/bin/openclaw"
_DEFAULT_TIMEOUT_S = 120.0


def one_shot(prompt: str, model: str | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Run a single inference turn against the active provider/model.

    Args:
        prompt: User message.
        model: Optional override `provider/model`. Defaults to active config.
        timeout: Subprocess timeout seconds (default 2 minutes).

    Returns:
        Dict with keys: ok, text, model, provider, transport, error?
    """
    if not prompt or not prompt.strip():
        return {"ok": False, "error": "prompt required"}
    if not model:
        provider, mdl = get_active_provider_model()
        if not provider or not mdl:
            return {"ok": False, "error": "No active provider/model — configure via Cấu hình AI"}
        model = f"{provider}/{mdl}"

    args = [
        _OPENCLAW_BIN,
        "capability",
        "model",
        "run",
        "--model",
        model,
        "--prompt",
        prompt,
        "--gateway",
        "--json",
    ]
    gateway_token = dotenv_get("OPENCLAW_GATEWAY_TOKEN") or ""
    env = {
        "HOME": "/opt/openclaw",
        "OPENCLAW_GATEWAY_TOKEN": gateway_token,
    }
    try:
        r = run_cmd(args, timeout=timeout, env=env)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat subprocess failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    if r.returncode != 0:
        return {
            "ok": False,
            "error": f"openclaw exited {r.returncode}",
            "stderr": (r.stderr or "")[:2000],
        }
    # openclaw emits the JSON object as the last line of stdout. Walk back to
    # find the start of the outermost JSON.
    raw = (r.stdout or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: find last balanced { ... }
        idx = raw.rfind("{")
        if idx == -1:
            return {"ok": False, "error": "could not parse openclaw output", "raw": raw[:2000]}
        try:
            parsed = json.loads(raw[idx:])
        except json.JSONDecodeError:
            return {"ok": False, "error": "could not parse openclaw output", "raw": raw[:2000]}
    if not parsed.get("ok"):
        return {
            "ok": False,
            "error": parsed.get("error", "openclaw returned ok=false"),
            "raw": parsed,
        }
    outputs = parsed.get("outputs") or []
    text = outputs[0].get("text", "") if outputs else ""
    return {
        "ok": True,
        "text": text,
        "model": parsed.get("model"),
        "provider": parsed.get("provider"),
        "transport": parsed.get("transport"),
    }
