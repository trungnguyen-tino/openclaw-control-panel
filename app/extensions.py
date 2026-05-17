"""Flask extension singletons (rate-limiter)."""

from __future__ import annotations

from flask import request
from flask_limiter import Limiter

from app.utils.ip_cidr_whitelist import get_client_ip, is_whitelisted_ip


def _rate_limit_key() -> str:
    return get_client_ip(request)


limiter: Limiter = Limiter(
    key_func=_rate_limit_key,
    storage_uri="memory://",
    default_limits=[],
    headers_enabled=True,
)


def _limit_exempt() -> bool:
    """flask-limiter pre-check hook — bypass for whitelisted CIDRs."""
    try:
        return is_whitelisted_ip(get_client_ip(request))
    except Exception:
        return False


limiter.request_filter(_limit_exempt)  # type: ignore[no-untyped-call]
