"""PKCE (Proof Key for Code Exchange) helpers — RFC 7636 S256.

Used by the ChatGPT Codex OAuth flow. Verifier is opaque high-entropy random;
challenge is the base64url(sha256(verifier)) without padding.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from app.config import OPENAI_CODEX_CLIENT_ID, OPENAI_CODEX_ISSUER

REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"


def gen_verifier(nbytes: int = 64) -> str:
    """Return a high-entropy verifier (43-128 chars per RFC 7636)."""
    return secrets.token_urlsafe(nbytes)


def s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorize_url(state: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": OPENAI_CODEX_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": SCOPE,
        "state": state,
    }
    return f"{OPENAI_CODEX_ISSUER}/oauth/authorize?{urlencode(params)}"


def extract_code_from_redirect(redirect_url: str) -> str | None:
    """Parse the `code` query param the user pastes back. Tolerant of full URL or just query."""
    if not redirect_url:
        return None
    from urllib.parse import parse_qs, urlsplit

    if "?" not in redirect_url and "=" in redirect_url:
        redirect_url = "?" + redirect_url
    q = parse_qs(urlsplit(redirect_url).query)
    val = q.get("code", [None])[0]
    return val
