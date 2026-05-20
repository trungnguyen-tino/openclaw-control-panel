"""Read/write `/opt/openclaw/config/openclaw.json` atomically + merge templates.

Critical property: provider switches MUST preserve `agents.list`, `bindings`,
`channels` from the active config — only `agents.defaults.model.primary` and
`models.providers.<id>` are replaced from the template.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app import config as _cfg

_CONFIG_MODE = 0o600
_WRITE_LOCK = threading.Lock()


def _config_path() -> Path:
    return _cfg.PATHS.config_file


def read() -> dict[str, Any]:
    p = _config_path()
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_atomic(data: dict[str, Any]) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp_path = tempfile.mkstemp(prefix=".openclaw.", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp_path, _CONFIG_MODE)
            os.replace(tmp_path, p)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise


def merge_template(
    current: dict[str, Any], template: dict[str, Any], provider: str, model: str
) -> dict[str, Any]:
    """Apply template into current, preserving multi-agent + routing state.

    - gateway, browser, agents.defaults.maxConcurrent etc. → template wins.
    - agents.list, bindings, channels → keep from current.
    - models.providers — merge provider-specific block from template.
    - agents.defaults.model.primary → `provider/model`.
    """
    merged = copy.deepcopy(template)
    # Preserve list / bindings / channels.
    if isinstance(current.get("agents"), dict) and isinstance(current["agents"].get("list"), list):
        merged.setdefault("agents", {})
        merged["agents"]["list"] = current["agents"]["list"]
    if "bindings" in current:
        merged["bindings"] = current["bindings"]
    if "channels" in current:
        merged["channels"] = current["channels"]
    # Set primary model. UI sends ids in `<provider>/<model>` form (matching
    # known_models), so strip the prefix before re-prepending to avoid
    # `openai-codex/openai-codex/gpt-5.4`.
    merged.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
    merged["agents"]["defaults"]["model"]["primary"] = compose_primary(provider, model)
    # Carry over any models.providers blocks already configured for OTHER providers
    # so the user can keep multi-provider routing alive.
    cur_models = (
        current.get("models", {}).get("providers", {})
        if isinstance(current.get("models"), dict)
        else {}
    )
    if cur_models:
        merged.setdefault("models", {}).setdefault("providers", {})
        for other_id, other_cfg in cur_models.items():
            if other_id != provider:
                merged["models"]["providers"].setdefault(other_id, other_cfg)
    return merged


def compose_primary(provider: str, model: str) -> str:
    """Build `agents.defaults.model.primary` = `<provider>/<bare-model>`.

    Accepts either bare model id (`gpt-5.4`) or already-prefixed (`openai-codex/gpt-5.4`)
    — returns the canonical single-prefix form either way.
    """
    prefix = f"{provider}/"
    bare = model[len(prefix) :] if model.startswith(prefix) else model
    return f"{provider}/{bare}"


def get_active_provider_model(cfg: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    """Inspect `agents.defaults.model.primary` like `groq/llama-3.3` → (provider, model)."""
    data = cfg if cfg is not None else read()
    primary = data.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
    if "/" in primary:
        provider, _, model = primary.partition("/")
        return provider or None, model or None
    return None, None
