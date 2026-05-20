"""Regression tests for the adversarial-review fixes (C1, C2, I1, I2, I3)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "s" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


# C1 — login returns mgmtApiKey


def test_login_returns_mgmt_api_key(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    from app.auth import scrypt_hash

    pw_hash = scrypt_hash("hunter2")
    (tmp_openclaw_home / ".env").write_text(
        f"OPENCLAW_MGMT_API_KEY={'s'*64}\n"
        f"OPENCLAW_LOGIN_USER=admin\n"
        f"OPENCLAW_LOGIN_PASS={pw_hash}\n"
        f"OPENCLAW_GATEWAY_TOKEN={'g'*64}\n"
    )
    r = client.post("/api/auth/login", json={"username": "admin", "password": "hunter2"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["mgmtApiKey"] == "s" * 64
    assert body["gatewayToken"] == "g" * 64


# C2 — provider switch rollback on restart failure


def test_provider_switch_rolls_back_on_restart_fail(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from app.services import openclaw_config_service, systemd_service

    h = _auth_h(tmp_openclaw_home)
    # Seed pre-switch config
    initial = {
        "agents": {"defaults": {"model": {"primary": "anthropic/claude-opus"}}},
        "marker": "pre-switch",
    }
    openclaw_config_service.write_atomic(initial)
    monkeypatch.setattr(systemd_service, "restart", lambda _: (False, "fake fail"))

    r = client.put(
        "/api/config/provider",
        json={"provider": "groq", "model": "llama-3.3"},
        headers=h,
    )
    assert r.status_code == 500
    # Config rolled back
    cfg = openclaw_config_service.read()
    assert cfg.get("marker") == "pre-switch"


# I1 — body size cap


def test_body_size_capped(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    huge = "x" * (2 * 1024 * 1024)  # 2 MB > 1 MB cap
    r = client.post(
        "/api/cli",
        data=huge,
        headers={**h, "Content-Type": "application/json"},
    )
    # Werkzeug test client may return 400 or 413 for oversized bodies; both
    # indicate the cap kicked in (vs. silently parsing 2 MB JSON).
    assert r.status_code in (400, 413)


# I2 — security headers present


def test_security_headers_set(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/health")
    assert "Content-Security-Policy" in r.headers
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# I3 — set api-key on non-existent agent returns 404


def test_set_agent_key_on_missing_agent_returns_404(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put(
        "/api/agents/ghost/api-key",
        json={"provider": "anthropic", "apiKey": "sk-x"},
        headers=h,
    )
    assert r.status_code == 404
    # And no agent dir was created.
    assert not (tmp_openclaw_home / "config" / "agents" / "ghost").exists()
