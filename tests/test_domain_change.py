"""Phase 08 — domain change + Caddy + env tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "z" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def stub_dns_and_caddy(monkeypatch: pytest.MonkeyPatch) -> dict:
    from app.services import (
        caddy_service,
        dns_check_service,
        domain_change_service,
        systemd_service,
    )

    state: dict = {"restart_caddy_calls": 0, "active": True}

    def fake_resolve(domain, timeout=5.0):
        return "1.2.3.4"

    def fake_public_ip():
        return "1.2.3.4"

    def fake_restart(_name):
        state["restart_caddy_calls"] += 1
        return True, ""

    monkeypatch.setattr(dns_check_service, "resolve_a", fake_resolve)
    monkeypatch.setattr(domain_change_service, "server_public_ip", fake_public_ip)
    monkeypatch.setattr(systemd_service, "restart", fake_restart)
    monkeypatch.setattr(systemd_service, "is_active", lambda _: state["active"])
    return state


def test_domain_change_writes_env_and_caddyfile(
    client, tmp_openclaw_home: Path, stub_dns_and_caddy
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put("/api/domain", json={"domain": "panel.example.com"}, headers=h)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["ssl"] == "letsencrypt"
    env_content = (tmp_openclaw_home / ".env").read_text()
    assert "DOMAIN=panel.example.com" in env_content
    # Caddyfile written
    caddyfile = tmp_openclaw_home / "Caddyfile"
    assert caddyfile.is_file()
    assert "{$DOMAIN" in caddyfile.read_text()
    assert stub_dns_and_caddy["restart_caddy_calls"] >= 1


def test_domain_change_invalid_format(
    client, tmp_openclaw_home: Path, stub_dns_and_caddy
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put("/api/domain", json={"domain": "not a domain!"}, headers=h)
    assert r.status_code == 400


def test_domain_change_rollback_on_caddy_fail(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    (tmp_openclaw_home / ".env").write_text(
        f"OPENCLAW_MGMT_API_KEY={'z'*64}\nDOMAIN=old.example.com\nCADDY_TLS=tls internal\n"
    )
    from app.services import dns_check_service, domain_change_service, systemd_service

    monkeypatch.setattr(dns_check_service, "resolve_a", lambda d, timeout=5.0: "1.2.3.4")
    monkeypatch.setattr(domain_change_service, "server_public_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(systemd_service, "restart", lambda _: (False, "caddy fail"))
    monkeypatch.setattr(systemd_service, "is_active", lambda _: False)
    r = client.put("/api/domain", json={"domain": "new.example.com"}, headers=h)
    assert r.status_code == 400
    body = r.get_json()
    assert body["rolledBack"] is True
    # .env rolled back
    env = (tmp_openclaw_home / ".env").read_text()
    assert "DOMAIN=old.example.com" in env


def test_env_locked_set_rejected(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put(
        "/api/env/OPENCLAW_MGMT_API_KEY",
        json={"value": "new"},
        headers=h,
    )
    assert r.status_code == 400


def test_env_locked_delete_rejected(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    for locked in ("OPENCLAW_GATEWAY_TOKEN", "OPENCLAW_VERSION", "OPENCLAW_GATEWAY_PORT"):
        r = client.delete(f"/api/env/{locked}", headers=h)
        assert r.status_code == 400, locked


def test_env_set_gateway_token_syncs_openclaw_json(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put(
        "/api/env/OPENCLAW_GATEWAY_TOKEN",
        json={"value": "new-token-xyz"},
        headers=h,
    )
    assert r.status_code == 200
    import json

    cfg = json.loads((tmp_openclaw_home / "config" / "openclaw.json").read_text())
    assert cfg["gateway"]["auth"]["token"] == "new-token-xyz"


def test_env_list_masks_sensitive(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    (tmp_openclaw_home / ".env").write_text(
        f"OPENCLAW_MGMT_API_KEY={'z'*64}\nDOMAIN=foo.com\nANTHROPIC_API_KEY=sk-ant-12345678abcd\n"
    )
    r = client.get("/api/env", headers=h)
    body = r.get_json()
    env = body["env"]
    assert env["DOMAIN"] == "foo.com"
    assert "..." in env["ANTHROPIC_API_KEY"]
    assert "..." in env["OPENCLAW_MGMT_API_KEY"]
