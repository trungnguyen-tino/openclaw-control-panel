"""Secret masking + timing-safe comparison helpers.

Mirrors `sanitizeKey` (source server.js:187-190) and the env-var masking logic
applied to responses for `/api/env` and `/api/config`.
"""

from __future__ import annotations

import hmac
import re

# Substring patterns that mark an env var as sensitive (case-insensitive).
_SENSITIVE_RE = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD|PASS|AUTH)", re.IGNORECASE)


def sanitize_key(value: str | None) -> str:
    """Return masked key — first 8 + `...` + last 4 if len >= 12, else `***`.

    Identical contract to source `sanitizeKey(key)` so JSON responses match.
    """
    if not value or len(value) < 12:
        return "***"
    return f"{value[:8]}...{value[-4:]}"


def mask_env_value(key: str, value: str | None) -> str:
    """Mask `value` only when `key` looks sensitive."""
    if value is None:
        return ""
    if _SENSITIVE_RE.search(key):
        return sanitize_key(value)
    return value


def timing_safe_compare(a: str, b: str) -> bool:
    """`hmac.compare_digest` over UTF-8 bytes — constant-time on equal-length input."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
