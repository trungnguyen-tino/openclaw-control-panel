"""HTTP-based API key validation per provider.

Source server.js shells out to `curl` for the tests; we use `requests` directly
which is safer (no shell injection) and lets us surface real error messages.

Each tester returns `(ok: bool, message: str)`. Network failures → `ok=False`.
"""

from __future__ import annotations

from typing import Final

import requests

from app.providers.known_models import PROVIDERS

_TIMEOUT_S: Final[float] = 10.0


def _test_bearer_models(url: str, api_key: str) -> tuple[bool, str]:
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=_TIMEOUT_S)
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return False, str(e)


def _test_anthropic(url: str, api_key: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=_TIMEOUT_S,
        )
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return False, str(e)


def _test_google(url: str, api_key: str) -> tuple[bool, str]:
    try:
        r = requests.get(url, params={"key": api_key}, timeout=_TIMEOUT_S)
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return False, str(e)


def _test_zhipu(url: str, api_key: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "glm-4.5-flash",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=_TIMEOUT_S,
        )
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return False, str(e)


def test_key(provider_id: str, api_key: str) -> tuple[bool, str]:
    p = PROVIDERS.get(provider_id)
    if not p:
        return False, f"Unknown provider '{provider_id}'"
    method = p.get("test_method", "bearer_models")
    url = p.get("test_url")
    if method == "none" or not url:
        return False, "Provider has no testable API key (OAuth or custom)"
    if not api_key:
        return False, "Missing apiKey"
    if method == "bearer_models":
        return _test_bearer_models(url, api_key)
    if method == "anthropic":
        return _test_anthropic(url, api_key)
    if method == "google_key_query":
        return _test_google(url, api_key)
    if method == "zhipu":
        return _test_zhipu(url, api_key)
    # Fallback to Bearer style.
    return _test_bearer_models(url, api_key)
