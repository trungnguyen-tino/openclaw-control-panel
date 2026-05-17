"""Load provider config templates from `app/providers/templates/<id>.json`.

Custom providers live under `/opt/openclaw/config/<id>.json` (handled by
`custom_provider_service`). This module is the source for built-ins only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.providers.known_models import PROVIDERS

_TEMPLATES_DIR = (Path(__file__).resolve().parent / "templates").resolve()


def template_path(provider_id: str) -> Path:
    return _TEMPLATES_DIR / f"{provider_id}.json"


def load_template(provider_id: str) -> dict[str, Any]:
    if provider_id not in PROVIDERS:
        raise KeyError(f"Unknown built-in provider: {provider_id}")
    path = template_path(provider_id)
    if not path.is_file():
        raise FileNotFoundError(f"Template missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_template_files() -> list[str]:
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _TEMPLATES_DIR.glob("*.json"))
