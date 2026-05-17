"""Phase 01 smoke — app factory boots, SPA fallback returns 404 only for /api/*."""

from __future__ import annotations


def test_app_boots(app) -> None:  # type: ignore[no-untyped-def]
    assert app is not None
    assert app.config["TESTING"] is True


def test_spa_fallback_for_unknown_path_returns_404_for_api(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_paths_use_env_override(tmp_openclaw_home) -> None:  # type: ignore[no-untyped-def]
    from app.config import PATHS

    assert PATHS.openclaw_home == tmp_openclaw_home
    assert PATHS.env_file == tmp_openclaw_home / ".env"
    assert PATHS.devices_pending == tmp_openclaw_home / "config" / "devices" / "pending.json"
