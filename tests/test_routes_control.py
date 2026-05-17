"""Phase 03 — control-route tests (restart/stop/start/upgrade/reset/self-update)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def stub_systemd(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Capture systemd calls without touching the host."""
    calls: dict[str, list] = {"restart": [], "stop": [], "start": []}
    from app.services import systemd_service

    def _restart(name: str) -> tuple[bool, str]:
        calls["restart"].append(name)
        return True, ""

    def _stop(name: str) -> tuple[bool, str]:
        calls["stop"].append(name)
        return True, ""

    def _start(name: str) -> tuple[bool, str]:
        calls["start"].append(name)
        return True, ""

    monkeypatch.setattr(systemd_service, "restart", _restart)
    monkeypatch.setattr(systemd_service, "stop", _stop)
    monkeypatch.setattr(systemd_service, "start", _start)
    return calls


def _seed_auth(tmp_home: Path) -> dict[str, str]:
    key = "c" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_restart_calls_systemctl(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.post("/api/restart", headers=h)
    assert r.status_code == 200
    assert stub_systemd["restart"] == ["openclaw"]


def test_stop_calls_systemctl(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.post("/api/stop", headers=h)
    assert r.status_code == 200
    assert stub_systemd["stop"] == ["openclaw"]


def test_rebuild_restarts_both(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.post("/api/rebuild", headers=h)
    assert r.status_code == 200
    assert "openclaw" in stub_systemd["restart"]
    assert "caddy" in stub_systemd["restart"]


def test_upgrade_returns_202_async(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    # Make sure we don't fork a real npm process.
    import app.routes.control_routes as ctrl

    monkeypatch.setattr(ctrl, "_run_upgrade_in_background", lambda: None)
    r = client.post("/api/upgrade", headers=h)
    assert r.status_code == 202
    body = r.get_json()
    assert body["async"] is True


def test_reset_requires_confirm_string(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    r = client.post("/api/reset", json={}, headers=h)
    assert r.status_code == 400
    r2 = client.post("/api/reset", json={"confirm": "wrong"}, headers=h)
    assert r2.status_code == 400


def test_reset_with_correct_confirm_clears_config(
    client, tmp_openclaw_home: Path, stub_systemd
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    config_dir = tmp_openclaw_home / "config"
    junk = config_dir / "junk.json"
    junk.write_text("{}")
    assert junk.exists()
    r = client.post("/api/reset", json={"confirm": "RESET"}, headers=h)
    assert r.status_code == 200
    assert not junk.exists()
    # Restart was called.
    assert "openclaw" in stub_systemd["restart"]


def test_self_update_returns_202(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    h = _seed_auth(tmp_openclaw_home)
    from app.services import self_update_service

    monkeypatch.setattr(self_update_service, "run_async", lambda tag: None)
    r = client.post("/api/self-update", json={"tag": "v1.0.0"}, headers=h)
    assert r.status_code == 202
    assert r.get_json()["tag"] == "v1.0.0"
