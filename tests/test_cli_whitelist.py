"""Phase 07 — CLI whitelist + parse tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.cli_whitelist import CliBlocked, parse


def test_allows_openclaw_commands() -> None:
    assert parse("openclaw status") == ["openclaw", "status"]


def test_allows_systemctl() -> None:
    assert parse("systemctl status openclaw")[0] == "systemctl"


def test_allows_journalctl_with_args() -> None:
    assert parse("journalctl -u openclaw -n 50") == [
        "journalctl",
        "-u",
        "openclaw",
        "-n",
        "50",
    ]


def test_allows_npm_update_prefix() -> None:
    assert parse("npm update -g openclaw") == ["npm", "update", "-g", "openclaw"]


def test_rejects_non_whitelisted_command() -> None:
    with pytest.raises(CliBlocked):
        parse("rm -rf /")
    with pytest.raises(CliBlocked):
        parse("cat /etc/passwd")


def test_rejects_metacharacters() -> None:
    for evil in (
        "openclaw status; rm -rf /",
        "openclaw status && rm",
        "openclaw `id`",
        'openclaw "$(curl evil)"',
        "openclaw status | grep root",
    ):
        with pytest.raises(CliBlocked):
            parse(evil)


def test_rejects_empty_command() -> None:
    with pytest.raises(CliBlocked):
        parse("")
    with pytest.raises(CliBlocked):
        parse("   ")


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "k" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_cli_route_blocks_metachars(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post("/api/cli", json={"command": "openclaw status; rm"}, headers=h)
    assert r.status_code == 400


def test_cli_route_returns_output(
    client, tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    from types import SimpleNamespace

    import app.routes.cli_routes as cli_routes

    fake = SimpleNamespace(returncode=0, stdout="version 1.0\n", stderr="")
    monkeypatch.setattr(cli_routes, "run_cmd", lambda parts, timeout=30: fake)
    r = client.post("/api/cli", json={"command": "openclaw --version"}, headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["exitCode"] == 0
    assert "version 1.0" in body["stdout"]
