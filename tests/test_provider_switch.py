"""Phase 04 — provider switch + custom provider lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def stub_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import systemd_service

    monkeypatch.setattr(systemd_service, "restart", lambda _: (True, ""))


def _seed_auth(tmp_home: Path) -> dict[str, str]:
    key = "p" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_get_providers_returns_builtin_catalog(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.get("/api/providers", headers=h)
    assert r.status_code == 200
    body = r.get_json()
    ids = {p["id"] for p in body["providers"]}
    # Must include the major providers + codex.
    for must in ("anthropic", "openai", "openai-codex", "google", "groq", "openrouter"):
        assert must in ids
    # 22 built-ins total (incl. openai-codex) — matches source PROVIDERS map.
    assert len([p for p in body["providers"] if not p.get("custom")]) == 22


def test_switch_provider_writes_config_and_restarts(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    # Pre-populate openclaw.json with some agent/binding state.
    (tmp_openclaw_home / "config" / "openclaw.json").write_text(
        json.dumps(
            {
                "agents": {"list": [{"id": "alpha", "default": True}], "defaults": {}},
                "bindings": [{"agentId": "alpha", "match": {"channel": "telegram"}}],
                "channels": {"telegram": {"enabled": True}},
            }
        )
    )
    r = client.put(
        "/api/config/provider",
        json={"provider": "groq", "model": "llama-3.3-70b-versatile"},
        headers=h,
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    cfg = json.loads((tmp_openclaw_home / "config" / "openclaw.json").read_text())
    # Provider+model updated.
    assert cfg["agents"]["defaults"]["model"]["primary"] == "groq/llama-3.3-70b-versatile"
    # Multi-agent + bindings preserved.
    assert cfg["agents"]["list"] == [{"id": "alpha", "default": True}]
    assert cfg["bindings"][0]["match"]["channel"] == "telegram"
    assert cfg["channels"]["telegram"]["enabled"] is True


def test_set_api_key_writes_env(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.put(
        "/api/config/api-key",
        json={"provider": "anthropic", "apiKey": "sk-ant-xxxx"},
        headers=h,
    )
    assert r.status_code == 200
    env = (tmp_openclaw_home / ".env").read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-xxxx" in env


def test_delete_api_key_removes_env(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    (tmp_openclaw_home / ".env").write_text(
        f"OPENCLAW_MGMT_API_KEY={'p' * 64}\nANTHROPIC_API_KEY=sk-old\n"
    )
    r = client.delete(
        "/api/config/api-key",
        json={"provider": "anthropic"},
        headers=h,
    )
    assert r.status_code == 200
    env = (tmp_openclaw_home / ".env").read_text()
    assert "ANTHROPIC_API_KEY" not in env


def test_test_key_calls_provider(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    from app.providers import key_tester

    monkeypatch.setattr(key_tester, "test_key", lambda p, k: (True, "OK"))
    r = client.post(
        "/api/config/test-key",
        json={"provider": "openai", "apiKey": "sk-xxx"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_custom_provider_lifecycle(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    create = client.post(
        "/api/config/custom-provider",
        json={
            "id": "myprovider",
            "baseUrl": "https://api.example.com/v1",
            "model": "model-a",
            "modelName": "Model A",
            "apiKey": "sk-xyz",
        },
        headers=h,
    )
    assert create.status_code == 201
    listing = client.get("/api/config/custom-providers", headers=h)
    assert listing.status_code == 200
    ids = {p["id"] for p in listing.get_json()["providers"]}
    assert "myprovider" in ids
    # Verify file written
    path = tmp_openclaw_home / "config" / "myprovider.json"
    assert path.is_file()
    delete = client.delete("/api/config/custom-provider/myprovider", headers=h)
    assert delete.status_code == 200
    assert not path.is_file()


def test_custom_provider_rejects_builtin_slug(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.post(
        "/api/config/custom-provider",
        json={
            "id": "anthropic",  # collides
            "baseUrl": "https://api.example.com/v1",
            "model": "x",
        },
        headers=h,
    )
    assert r.status_code == 400
