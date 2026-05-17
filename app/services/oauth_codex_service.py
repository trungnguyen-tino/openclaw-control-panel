"""ChatGPT Codex OAuth flow + token refresh.

In-memory PKCE session store (matches source — sessions evaporate on restart).
Token exchange + refresh against `auth.openai.com/oauth/token`.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app import config as _cfg
from app.config import OPENAI_CODEX_CLIENT_ID, OPENAI_CODEX_ISSUER
from app.providers.known_models import PROVIDERS
from app.services import auth_profiles_service, pkce_service

log = logging.getLogger("openclaw.oauth_codex")

SESSION_TTL_MS = 10 * 60 * 1000
TOKEN_URL = f"{OPENAI_CODEX_ISSUER}/oauth/token"


@dataclass
class _PkceSession:
    session_id: str
    verifier: str
    agent_id: str
    created_at_ms: int
    expires_at_ms: int


class _SessionStore:
    def __init__(self) -> None:
        self._d: dict[str, _PkceSession] = {}
        self._lock = threading.Lock()

    def add(self, s: _PkceSession) -> None:
        with self._lock:
            self._d[s.session_id] = s

    def pop(self, sid: str) -> _PkceSession | None:
        with self._lock:
            s = self._d.pop(sid, None)
        if not s:
            return None
        if s.expires_at_ms < _now_ms():
            return None
        return s

    def gc(self) -> int:
        now = _now_ms()
        with self._lock:
            stale = [k for k, v in self._d.items() if v.expires_at_ms < now]
            for k in stale:
                del self._d[k]
        return len(stale)


_store = _SessionStore()


def _now_ms() -> int:
    return int(time.time() * 1000)


def start_session(agent_id: str = "default") -> dict[str, Any]:
    verifier = pkce_service.gen_verifier()
    challenge = pkce_service.s256_challenge(verifier)
    sid = secrets.token_urlsafe(32)
    now = _now_ms()
    _store.add(
        _PkceSession(
            session_id=sid,
            verifier=verifier,
            agent_id=agent_id,
            created_at_ms=now,
            expires_at_ms=now + SESSION_TTL_MS,
        )
    )
    codex = PROVIDERS.get("openai-codex") or {}
    return {
        "sessionId": sid,
        "oauthUrl": pkce_service.build_authorize_url(sid, challenge),
        "models": list(codex.get("known_models", [])),
        "instructions": (
            "Open the oauthUrl in a browser, sign in to ChatGPT, then paste the entire "
            "redirect URL (or just the `code` query param) into the complete endpoint."
        ),
        "sessionExpiresIn": SESSION_TTL_MS // 1000,
    }


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload without signature verification (TLS-trust only)."""
    try:
        _, payload, _ = token.split(".")
        # Pad to multiple of 4.
        pad = "=" * ((4 - len(payload) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(payload + pad).decode("utf-8"))
    except Exception:
        return {}


def complete_session(
    session_id: str,
    redirect_url: str,
    model: str | None = None,
    switch_provider: bool = False,
) -> dict[str, Any]:
    s = _store.pop(session_id)
    if not s:
        return {"ok": False, "error": "Session expired or unknown"}
    code = pkce_service.extract_code_from_redirect(redirect_url)
    if not code:
        return {"ok": False, "error": "Could not parse `code` from redirect URL"}
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": OPENAI_CODEX_CLIENT_ID,
                "code": code,
                "code_verifier": s.verifier,
                "redirect_uri": pkce_service.REDIRECT_URI,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        return {"ok": False, "error": f"Token endpoint network error: {e}"}
    if resp.status_code != 200:
        return {
            "ok": False,
            "error": f"Token endpoint HTTP {resp.status_code}: {resp.text[:200]}",
        }
    body = resp.json()
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    expires_in = int(body.get("expires_in", 0))
    id_token = body.get("id_token", "")
    if not access or not refresh:
        return {"ok": False, "error": "Token response missing access/refresh"}
    claims = _decode_jwt_payload(id_token)
    email = claims.get("email") or "unknown"
    account_id = (
        claims.get("https://api.openai.com/auth", {}).get("user_id")
        if isinstance(claims.get("https://api.openai.com/auth"), dict)
        else None
    ) or claims.get("sub", "")
    profile_key = f"openai-codex:{email}"
    auth_profiles_service.set_oauth_profile(
        s.agent_id,
        profile_key,
        {
            "type": "oauth",
            "provider": "openai-codex",
            "access": access,
            "refresh": refresh,
            "expires": _now_ms() + expires_in * 1000,
            "accountId": account_id,
            "email": email,
        },
    )
    switched = False
    if switch_provider:
        from app.services import provider_service

        chosen = model or "gpt-5.4"
        provider_service.switch_provider("openai-codex", chosen)
        switched = True
    return {
        "ok": True,
        "profileKey": profile_key,
        "accountId": account_id,
        "email": email,
        "switchedProvider": switched,
        "model": model,
    }


def refresh_profile(agent_id: str, profile_key: str) -> bool:
    profiles = auth_profiles_service.list_profiles(agent_id)
    prof = profiles.get(profile_key)
    if not prof or prof.get("dead"):
        return False
    refresh = prof.get("refresh")
    if not refresh:
        return False
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": OPENAI_CODEX_CLIENT_ID,
                "refresh_token": refresh,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        log.warning("oauth.refresh network agent=%s key=%s err=%s", agent_id, profile_key, e)
        return False
    if resp.status_code != 200:
        body = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
        if body.get("error") == "invalid_grant":
            prof["dead"] = True
            prof["deadReason"] = "invalid_grant"
            auth_profiles_service.set_oauth_profile(agent_id, profile_key, prof)
            log.warning("oauth.refresh dead agent=%s key=%s", agent_id, profile_key)
        return False
    data = resp.json()
    prof["access"] = data.get("access_token", prof.get("access"))
    if data.get("refresh_token"):
        prof["refresh"] = data["refresh_token"]
    prof["expires"] = _now_ms() + int(data.get("expires_in", 0)) * 1000
    auth_profiles_service.set_oauth_profile(agent_id, profile_key, prof)
    log.info("oauth.refresh ok agent=%s key=%s", agent_id, profile_key)
    return True


def list_oauth_profiles_for_all_agents() -> list[tuple[str, str, dict[str, Any]]]:
    """Yield (agent_id, profile_key, profile) across every agent's auth-profiles."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    agents_dir: Path = _cfg.PATHS.agents_dir
    if not agents_dir.is_dir():
        return out
    for agent_path in agents_dir.iterdir():
        if not agent_path.is_dir():
            continue
        agent_id = agent_path.name
        if not auth_profiles_service.AGENT_ID_RE.match(agent_id):
            continue
        for key, prof in auth_profiles_service.list_profiles(agent_id).items():
            if prof.get("type") == "oauth":
                out.append((agent_id, key, prof))
    return out
