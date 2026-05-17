"""CIDR-based IP whitelist used for rate-limit bypass.

Mirrors source server.js:87-93 (tinohost subnets + loopback) and provides a
`get_client_ip(request)` helper that respects `X-Forwarded-For` only when the
direct peer is loopback (Caddy is the only legitimate proxy in our topology).
"""

from __future__ import annotations

import ipaddress
from typing import Any

from app.config import WHITELIST_CIDRS

_WHITELIST_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(c, strict=False) for c in WHITELIST_CIDRS
)

_TRUSTED_PROXIES: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(c, strict=False) for c in ("127.0.0.1/32", "::1/128")
)


def is_whitelisted_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _WHITELIST_NETS)


def get_client_ip(request: Any) -> str:
    """Return the originating client IP.

    Trust `X-Forwarded-For` only when the direct connection comes from
    loopback (Caddy proxy). Else fall back to `request.remote_addr` to prevent
    header spoofing from internet-facing clients.
    """
    remote = request.remote_addr or "127.0.0.1"
    try:
        remote_addr = ipaddress.ip_address(remote)
    except ValueError:
        return remote
    is_trusted_proxy = any(remote_addr in net for net in _TRUSTED_PROXIES)
    if is_trusted_proxy:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return remote
