"""DNS-over-HTTPS lookup via Cloudflare 1.1.1.1.

Used by `/api/info`, `/api/domain` (validation), and install-time DNS gate.
Cached for 30s to avoid hammering DoH on every dashboard request.
"""

from __future__ import annotations

import time
from typing import Any

import requests

_DOH_URL = "https://1.1.1.1/dns-query"
_CACHE_TTL = 30.0
_cache: dict[str, tuple[float, str | None]] = {}


def _cache_get(key: str) -> tuple[bool, str | None]:
    ts_value = _cache.get(key)
    if not ts_value:
        return False, None
    ts, value = ts_value
    if time.time() - ts > _CACHE_TTL:
        _cache.pop(key, None)
        return False, None
    return True, value


def _cache_set(key: str, value: str | None) -> None:
    _cache[key] = (time.time(), value)


def resolve_a(domain: str, timeout: float = 5.0) -> str | None:
    """Return first A-record IP, or None if NXDOMAIN / timeout / network error."""
    domain = domain.strip().lower()
    if not domain:
        return None
    hit, cached = _cache_get(domain)
    if hit:
        return cached
    try:
        r = requests.get(
            _DOH_URL,
            params={"name": domain, "type": "A"},
            headers={"Accept": "application/dns-json"},
            timeout=timeout,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        answers = data.get("Answer") or []
        for ans in answers:
            if ans.get("type") == 1 and ans.get("data"):
                ip = str(ans["data"])
                _cache_set(domain, ip)
                return ip
    except Exception:
        return None
    _cache_set(domain, None)
    return None


def clear_cache() -> None:
    _cache.clear()
