"""Phase 03 — info/status/version/system/logs/domain route tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mock_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub systemctl + journalctl so tests never shell out."""
    from app.services import journalctl_service, systemd_service

    monkeypatch.setattr(systemd_service, "is_active", lambda _: True)
    monkeypatch.setattr(systemd_service, "started_at", lambda _: None)
    monkeypatch.setattr(systemd_service, "restart", lambda _: (True, "ok"))
    monkeypatch.setattr(systemd_service, "stop", lambda _: (True, "ok"))
    monkeypatch.setattr(systemd_service, "start", lambda _: (True, "ok"))
    from app.config import ALLOWED_SERVICES

    def _fake_tail(service: str, lines: int = 100) -> list[str]:
        if service not in ALLOWED_SERVICES:
            raise ValueError(f"Service '{service}' not in whitelist")
        if not isinstance(lines, int) or lines < 1 or lines > 1000:
            raise ValueError("lines must be 1..1000")
        return [f"line-{i}" for i in range(lines)]

    monkeypatch.setattr(journalctl_service, "tail", _fake_tail)


def _key() -> str:
    return "k" * 64


def _auth_header(tmp_home: Path) -> dict[str, str]:
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={_key()}\nDOMAIN=panel.example.com\n")
    return {"Authorization": f"Bearer {_key()}"}


def test_info_requires_bearer(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/info")
    # Either 401 (key configured) or 503 (key absent) — both lock out anon.
    assert r.status_code in (401, 503)


def test_info_returns_expected_shape(
    client, tmp_openclaw_home: Path, mock_systemd
) -> None:  # type: ignore[no-untyped-def]
    from app.services import dns_check_service

    dns_check_service.clear_cache()
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/info", headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["domain"] == "panel.example.com"
    assert body["dashboardUrl"].startswith("https://")
    assert body["mgmtApiKey"] != _key()  # masked


def test_status_endpoint(client, tmp_openclaw_home: Path, mock_systemd) -> None:  # type: ignore[no-untyped-def]
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/status", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["openclaw"]["status"] == "active"
    assert body["caddy"]["status"] == "active"


def test_system_endpoint_returns_metrics(
    client, tmp_openclaw_home: Path, mock_systemd
) -> None:  # type: ignore[no-untyped-def]
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/system", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert "memory" in body and "total" in body["memory"]
    assert "disk" in body and "free" in body["disk"]
    assert "hostname" in body


def test_logs_validates_service_whitelist(
    client, tmp_openclaw_home: Path, mock_systemd
) -> None:  # type: ignore[no-untyped-def]
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/logs?service=root", headers=headers)
    assert r.status_code == 400


def test_logs_returns_lines(
    client, tmp_openclaw_home: Path, mock_systemd
) -> None:  # type: ignore[no-untyped-def]
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/logs?service=openclaw&lines=50", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["service"] == "openclaw"
    assert body["lines"] == 50


def test_logs_rejects_huge_lines(
    client, tmp_openclaw_home: Path, mock_systemd
) -> None:  # type: ignore[no-untyped-def]
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/logs?service=openclaw&lines=99999", headers=headers)
    assert r.status_code == 400


def test_domain_endpoint(client, tmp_openclaw_home: Path, mock_systemd) -> None:  # type: ignore[no-untyped-def]
    from app.services import dns_check_service

    dns_check_service.clear_cache()
    headers = _auth_header(tmp_openclaw_home)
    r = client.get("/api/domain", headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["domain"] == "panel.example.com"
    assert "ssl" in body
