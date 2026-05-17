"""Phase 05 — agent CRUD + auth-profiles tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "g" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_create_and_list_agent(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    create = client.post("/api/agents", json={"id": "alpha", "name": "Alpha"}, headers=h)
    assert create.status_code == 201
    listing = client.get("/api/agents", headers=h)
    body = listing.get_json()
    ids = {a["id"] for a in body["agents"]}
    assert "alpha" in ids
    # First agent should be default automatically.
    assert any(a["id"] == "alpha" and a["default"] for a in body["agents"])


def test_cannot_delete_last_agent(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post("/api/agents", json={"id": "solo"}, headers=h)
    r = client.delete("/api/agents/solo", headers=h)
    assert r.status_code == 400


def test_cannot_delete_default_agent(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post("/api/agents", json={"id": "alpha"}, headers=h)
    client.post("/api/agents", json={"id": "beta"}, headers=h)
    r = client.delete("/api/agents/alpha", headers=h)  # alpha is default
    assert r.status_code == 400


def test_set_default_enforces_single(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post("/api/agents", json={"id": "alpha"}, headers=h)
    client.post("/api/agents", json={"id": "beta"}, headers=h)
    r = client.put("/api/agents/beta/default", headers=h)
    assert r.status_code == 200
    listing = client.get("/api/agents", headers=h)
    agents = listing.get_json()["agents"]
    defaults = [a["id"] for a in agents if a["default"]]
    assert defaults == ["beta"]


def test_agent_api_key_writes_auth_profiles(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post("/api/agents", json={"id": "alpha"}, headers=h)
    r = client.put(
        "/api/agents/alpha/api-key",
        json={"provider": "anthropic", "apiKey": "sk-ant-xxxx"},
        headers=h,
    )
    assert r.status_code == 200
    auth_file = (
        tmp_openclaw_home / "config" / "agents" / "alpha" / "agent" / "auth-profiles.json"
    )
    data = json.loads(auth_file.read_text())
    assert "anthropic:manual" in data["profiles"]
    assert data["profiles"]["anthropic:manual"]["key"] == "sk-ant-xxxx"
    # .env should NOT contain ANTHROPIC_API_KEY (per-agent isolation).
    env = (tmp_openclaw_home / ".env").read_text()
    assert "ANTHROPIC_API_KEY" not in env


def test_get_agent_masks_keys(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post("/api/agents", json={"id": "alpha"}, headers=h)
    client.put(
        "/api/agents/alpha/api-key",
        json={"provider": "anthropic", "apiKey": "sk-ant-LONG-VALUE-1234"},
        headers=h,
    )
    r = client.get("/api/agents/alpha/api-key", headers=h)
    body = r.get_json()
    masked = body["profiles"]["anthropic:manual"]["key"]
    assert "sk-ant-LONG-VALUE-1234" not in masked
    assert "..." in masked


def test_invalid_agent_id_rejected(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post("/api/agents", json={"id": "BAD ID!"}, headers=h)
    assert r.status_code == 400


def test_malformed_auth_profiles_repaired(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    from app.services import auth_profiles_service

    # Set up agent dir manually with corrupt JSON.
    agent_dir = tmp_openclaw_home / "config" / "agents" / "broken" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "auth-profiles.json").write_text("{not json")
    data = auth_profiles_service.read("broken")
    assert data == {"profiles": {}}
