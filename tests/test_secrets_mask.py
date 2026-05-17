"""Phase 02 — sanitize_key + mask_env_value tests."""

from __future__ import annotations

from app.utils.secrets_mask import (
    mask_env_value,
    sanitize_key,
    timing_safe_compare,
)


def test_sanitize_key_long() -> None:
    s = sanitize_key("0123456789abcdef0123")
    assert s == "01234567...0123"


def test_sanitize_key_short_returns_stars() -> None:
    assert sanitize_key("short") == "***"
    assert sanitize_key("") == "***"
    assert sanitize_key(None) == "***"


def test_mask_env_value_masks_sensitive_keys() -> None:
    assert "..." in mask_env_value("ANTHROPIC_API_KEY", "sk-abcdef1234567890")
    assert "..." in mask_env_value("OPENCLAW_GATEWAY_TOKEN", "0123456789abcdef0123")
    assert "..." in mask_env_value("TELEGRAM_BOT_TOKEN", "1234567890:abcdefghij")


def test_mask_env_value_passes_non_sensitive() -> None:
    assert mask_env_value("DOMAIN", "example.com") == "example.com"
    assert mask_env_value("OPENCLAW_GATEWAY_PORT", "18789") == "18789"


def test_timing_safe_compare() -> None:
    assert timing_safe_compare("abc", "abc") is True
    assert timing_safe_compare("abc", "abd") is False
    assert timing_safe_compare("", "") is True
    assert timing_safe_compare("abc", "abcd") is False
