"""Phase 02 — CIDR whitelist + client IP extraction tests."""

from __future__ import annotations

from unittest.mock import Mock

from app.utils.ip_cidr_whitelist import get_client_ip, is_whitelisted_ip


def test_loopback_is_whitelisted() -> None:
    assert is_whitelisted_ip("127.0.0.1") is True
    assert is_whitelisted_ip("::1") is True


def test_tinohost_cidrs_whitelisted() -> None:
    assert is_whitelisted_ip("103.85.156.1") is True
    assert is_whitelisted_ip("103.234.20.50") is True
    assert is_whitelisted_ip("45.117.180.99") is True


def test_public_ip_not_whitelisted() -> None:
    assert is_whitelisted_ip("8.8.8.8") is False
    assert is_whitelisted_ip("198.51.100.5") is False


def test_invalid_ip_returns_false() -> None:
    assert is_whitelisted_ip("not-an-ip") is False
    assert is_whitelisted_ip("") is False


def test_get_client_ip_uses_remote_addr_for_public_peers() -> None:
    req = Mock()
    req.remote_addr = "198.51.100.5"
    req.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
    # Public peer → don't trust XFF
    assert get_client_ip(req) == "198.51.100.5"


def test_get_client_ip_honors_xff_from_loopback() -> None:
    req = Mock()
    req.remote_addr = "127.0.0.1"
    req.headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    assert get_client_ip(req) == "203.0.113.10"


def test_get_client_ip_falls_back_when_no_xff() -> None:
    req = Mock()
    req.remote_addr = "127.0.0.1"
    req.headers = {}
    assert get_client_ip(req) == "127.0.0.1"
