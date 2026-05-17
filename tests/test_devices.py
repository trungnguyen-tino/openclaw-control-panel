"""Phase 07 — device pairing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _auth_h(tmp_home: Path, key_char: str = "d") -> dict[str, str]:
    key = key_char * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_list_devices_empty(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.get("/api/devices", headers=h)
    body = r.get_json()
    assert body["pending"] == []
    assert body["paired"] == []


def test_approve_moves_pending_to_paired(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    # Seed pending.json
    pending = tmp_openclaw_home / "config" / "devices" / "pending.json"
    pending.write_text(
        json.dumps(
            {
                "uuid-1": {
                    "deviceId": "uuid-1",
                    "model": "Pixel 9",
                    "roles": ["operator"],
                    "createdAtMs": 1700000000000,
                }
            }
        )
    )
    r = client.post("/api/devices/approve/uuid-1", headers=h)
    assert r.status_code == 200
    paired = json.loads((tmp_openclaw_home / "config" / "devices" / "paired.json").read_text())
    assert "uuid-1" in paired
    assert "operator" in paired["uuid-1"]["tokens"]
    assert paired["uuid-1"]["tokens"]["operator"]["token"]


def test_approve_nonexistent_returns_404(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post("/api/devices/approve/nope", headers=h)
    assert r.status_code == 404


def test_pair_public_invalid_token(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    (tmp_openclaw_home / ".env").write_text(
        "OPENCLAW_MGMT_API_KEY=" + "x" * 64 + "\nOPENCLAW_GATEWAY_TOKEN=" + "a" * 64 + "\n"
    )
    r = client.get("/pair?token=wrong")
    assert r.status_code == 401


def test_pair_public_valid_token_redirects(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    gw = "g" * 64
    (tmp_openclaw_home / ".env").write_text(
        f"OPENCLAW_MGMT_API_KEY={'x'*64}\nOPENCLAW_GATEWAY_TOKEN={gw}\nDOMAIN=panel.example.com\n"
    )
    # Don't really spawn the poller thread.
    from app.services import pairing_polling_service

    activate_calls: list[bool] = []
    monkeypatch.setattr(
        pairing_polling_service.get_poller(),
        "activate",
        lambda: activate_calls.append(True),
    )
    r = client.get(f"/pair?token={gw}", follow_redirects=False)
    assert r.status_code == 302
    assert "panel.example.com" in r.headers["Location"]
    assert activate_calls == [True]
