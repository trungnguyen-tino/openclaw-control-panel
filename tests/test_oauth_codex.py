"""Phase 06 — OAuth Codex (PKCE + token exchange + refresh) tests."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import oauth_codex_service, pkce_service

# -- PKCE helpers -----------------------------------------------------------


def test_s256_challenge_matches_rfc7636() -> None:
    v = "abcdef" * 10
    expected = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    assert pkce_service.s256_challenge(v) == expected


def test_build_authorize_url_contains_required_params() -> None:
    url = pkce_service.build_authorize_url("state-x", "chal-y")
    for must in (
        "response_type=code",
        "code_challenge=chal-y",
        "state=state-x",
        "code_challenge_method=S256",
    ):
        assert must in url


def test_extract_code_handles_full_redirect_url() -> None:
    code = pkce_service.extract_code_from_redirect(
        "http://localhost:1455/auth/callback?code=ABC&state=X"
    )
    assert code == "ABC"


def test_extract_code_handles_query_only() -> None:
    assert pkce_service.extract_code_from_redirect("code=ABC&state=X") == "ABC"


# -- Session store ---------------------------------------------------------


def test_start_session_returns_url_and_models() -> None:
    info = oauth_codex_service.start_session("default")
    assert info["sessionId"]
    assert info["oauthUrl"].startswith("https://")
    assert len(info["models"]) > 0
    # Session can be retrieved + popped.
    s = oauth_codex_service._store.pop(info["sessionId"])
    assert s is not None


def test_session_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    # Insert an already-expired session.
    info = oauth_codex_service.start_session("agentX")
    # Force expiry: monkeypatch _now_ms.
    monkeypatch.setattr(
        oauth_codex_service,
        "_now_ms",
        lambda: time.time() * 1000 + oauth_codex_service.SESSION_TTL_MS + 1000,
    )
    assert oauth_codex_service._store.pop(info["sessionId"]) is None


# -- complete_session end-to-end -------------------------------------------


def _fake_id_token(email: str, sub: str = "user-1") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"email": email, "sub": sub}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}."


def test_complete_session_writes_oauth_profile(
    tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = oauth_codex_service.start_session("alpha")
    sid = info["sessionId"]
    # Mock the token endpoint.
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "access-xyz",
        "refresh_token": "refresh-xyz",
        "expires_in": 3600,
        "id_token": _fake_id_token("alice@example.com"),
    }
    monkeypatch.setattr(
        oauth_codex_service.requests,
        "post",
        lambda *a, **kw: mock_resp,
    )
    # Pre-create agent dir so write_atomic has somewhere to land.
    (tmp_openclaw_home / "config" / "agents" / "alpha" / "agent").mkdir(parents=True)
    result = oauth_codex_service.complete_session(sid, "code=ABC&state=" + sid)
    assert result["ok"] is True
    assert result["email"] == "alice@example.com"
    profile_path = (
        tmp_openclaw_home / "config" / "agents" / "alpha" / "agent" / "auth-profiles.json"
    )
    data = json.loads(profile_path.read_text())
    prof = data["profiles"]["openai-codex:alice@example.com"]
    assert prof["access"] == "access-xyz"
    assert prof["refresh"] == "refresh-xyz"
    assert prof["type"] == "oauth"


def test_complete_session_unknown_returns_error() -> None:
    r = oauth_codex_service.complete_session("not-a-session", "code=ABC")
    assert r["ok"] is False


# -- refresh_profile -------------------------------------------------------


def test_refresh_profile_updates_token(
    tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import auth_profiles_service

    agent_id = "beta"
    (tmp_openclaw_home / "config" / "agents" / agent_id / "agent").mkdir(parents=True)
    auth_profiles_service.set_oauth_profile(
        agent_id,
        "openai-codex:bob@example.com",
        {
            "type": "oauth",
            "provider": "openai-codex",
            "access": "old-access",
            "refresh": "refresh-token",
            "expires": 0,
            "accountId": "user-2",
        },
    )
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "new-access", "expires_in": 3600}
    monkeypatch.setattr(oauth_codex_service.requests, "post", lambda *a, **kw: mock_resp)
    ok = oauth_codex_service.refresh_profile(agent_id, "openai-codex:bob@example.com")
    assert ok is True
    profiles = auth_profiles_service.list_profiles(agent_id)
    assert profiles["openai-codex:bob@example.com"]["access"] == "new-access"


def test_refresh_marks_invalid_grant_dead(
    tmp_openclaw_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import auth_profiles_service

    agent_id = "gamma"
    (tmp_openclaw_home / "config" / "agents" / agent_id / "agent").mkdir(parents=True)
    auth_profiles_service.set_oauth_profile(
        agent_id,
        "openai-codex:eve@example.com",
        {
            "type": "oauth",
            "provider": "openai-codex",
            "access": "x",
            "refresh": "dead-refresh",
            "expires": 0,
        },
    )
    mock_resp = Mock()
    mock_resp.status_code = 400
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {"error": "invalid_grant"}
    monkeypatch.setattr(oauth_codex_service.requests, "post", lambda *a, **kw: mock_resp)
    ok = oauth_codex_service.refresh_profile(agent_id, "openai-codex:eve@example.com")
    assert ok is False
    profiles = auth_profiles_service.list_profiles(agent_id)
    assert profiles["openai-codex:eve@example.com"].get("dead") is True


# -- Routes ----------------------------------------------------------------


def test_start_endpoint(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    key = "o" * 64
    (tmp_openclaw_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    r = client.post(
        "/api/config/chatgpt-oauth/start",
        json={"agentId": "default"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["sessionId"]
    assert body["oauthUrl"].startswith("https://")
