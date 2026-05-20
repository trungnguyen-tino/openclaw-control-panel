"""Phase 05 / multi-account — channel CRUD via openclaw channels CLI wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def stub_channels(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Stub the openclaw_channels_service so tests don't shell out."""
    calls: dict[str, list] = {"add": [], "remove": [], "list": 0}
    from app.services import openclaw_channels_service, systemd_service

    def fake_add(channel: str, account: str, fields: dict) -> tuple[bool, str]:
        calls["add"].append((channel, account, fields))
        return True, "ok"

    def fake_remove(channel: str, account: str) -> tuple[bool, str]:
        calls["remove"].append((channel, account))
        return True, "ok"

    def fake_list() -> dict:
        calls["list"] += 1
        return {
            "telegram": {
                "label": "Telegram",
                "installed": True,
                "origin": "configured",
                "accounts": [{"id": "default", "label": "default"}],
                "fields": [],
            }
        }

    monkeypatch.setattr(openclaw_channels_service, "add_account", fake_add)
    monkeypatch.setattr(openclaw_channels_service, "remove_account", fake_remove)
    monkeypatch.setattr(openclaw_channels_service, "list_channels", fake_list)
    monkeypatch.setattr(systemd_service, "restart", lambda _: (True, ""))
    return calls


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "c" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_list_channels_returns_account_arrays(
    client, tmp_openclaw_home: Path, stub_channels
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.get("/api/channels", headers=h)
    body = r.get_json()["channels"]
    assert "telegram" in body
    assert body["telegram"]["accounts"][0]["id"] == "default"


def test_get_schema_returns_supported_channels(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.get("/api/channels/schema", headers=h)
    body = r.get_json()["schema"]
    for must in ("telegram", "discord", "slack", "whatsapp", "matrix", "zalo"):
        assert must in body
    # Telegram needs token field (matches openclaw CLI --token flag)
    assert any(f["key"] == "token" for f in body["telegram"]["fields"])


def test_add_account_invokes_cli_then_restart(
    client, tmp_openclaw_home: Path, stub_channels
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post(
        "/api/channels/telegram/accounts",
        json={"account_id": "bot1", "token": "123:abc", "name": "Bot One"},
        headers=h,
    )
    assert r.status_code == 201
    assert stub_channels["add"] == [("telegram", "bot1", {"token": "123:abc", "name": "Bot One"})]


def test_add_account_rejects_unknown_channel(
    client, tmp_openclaw_home: Path
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post(
        "/api/channels/snapchat/accounts",
        json={"account_id": "x", "bot_token": "y"},
        headers=h,
    )
    assert r.status_code == 404


def test_add_account_requires_account_id(
    client, tmp_openclaw_home: Path, stub_channels
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post(
        "/api/channels/telegram/accounts",
        json={"token": "y"},
        headers=h,
    )
    assert r.status_code == 400


def test_remove_account(client, tmp_openclaw_home: Path, stub_channels) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.delete("/api/channels/telegram/accounts/bot1", headers=h)
    assert r.status_code == 200
    assert stub_channels["remove"] == [("telegram", "bot1")]


def test_legacy_put_maps_to_default_account(
    client, tmp_openclaw_home: Path, stub_channels
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.put(
        "/api/channels/telegram",
        json={"token": "legacy-token"},
        headers=h,
    )
    assert r.status_code == 200
    # legacy `token` field passes through unchanged; account_id = "default"
    ch, account, fields = stub_channels["add"][0]
    assert ch == "telegram"
    assert account == "default"
    assert fields.get("token") == "legacy-token"


def test_legacy_delete_maps_to_default_account(
    client, tmp_openclaw_home: Path, stub_channels
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.delete("/api/channels/telegram", headers=h)
    assert r.status_code == 200
    assert stub_channels["remove"] == [("telegram", "default")]
