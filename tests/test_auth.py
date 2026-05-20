"""Phase 02 — scrypt + Bearer decorator + rate-limit tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from flask import Blueprint, Flask

from app.auth import (
    clear_auth_failures,
    is_ip_blocked,
    record_auth_failure,
    require_bearer,
    scrypt_hash,
    scrypt_verify,
)
from app.config import MAX_AUTH_FAILURES

# -- scrypt parity ----------------------------------------------------------


def test_scrypt_hash_roundtrip() -> None:
    h = scrypt_hash("hunter2")
    assert ":" in h
    assert scrypt_verify(h, "hunter2") is True
    assert scrypt_verify(h, "wrong") is False


def test_scrypt_verify_known_source_format() -> None:
    """Hash created with source params (N=16384, r=8, p=1, dklen=64) verifies."""
    pw = "s3cr3t!"
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    derived = hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=64)
    stored = f"{salt.hex()}:{derived.hex()}"
    assert scrypt_verify(stored, pw) is True
    assert scrypt_verify(stored, "other") is False


def test_scrypt_verify_malformed_returns_false() -> None:
    assert scrypt_verify("", "x") is False
    assert scrypt_verify("nocolon", "x") is False
    assert scrypt_verify("zz:zz", "x") is False  # invalid hex


# -- Rate-limit counter -----------------------------------------------------


def test_rate_limit_blocks_after_threshold() -> None:
    ip = "203.0.113.5"
    clear_auth_failures(ip)
    for _ in range(MAX_AUTH_FAILURES):
        record_auth_failure(ip)
    blocked, retry = is_ip_blocked(ip)
    assert blocked is True
    assert retry > 0
    clear_auth_failures(ip)


def test_whitelisted_ip_never_blocked() -> None:
    ip = "127.0.0.1"
    for _ in range(MAX_AUTH_FAILURES + 5):
        record_auth_failure(ip)
    blocked, _ = is_ip_blocked(ip)
    assert blocked is False


# -- Bearer decorator integration ------------------------------------------


def _make_app_with_protected_route(key: str, tmp_home: Path) -> Flask:
    from app import create_app

    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    flask_app = create_app({"TESTING": True})

    bp = Blueprint("test_protected", __name__)

    @bp.route("/api/protected", methods=["GET"])
    @require_bearer
    def protected():  # type: ignore[no-untyped-def]
        return {"ok": True, "secret": "ping"}

    flask_app.register_blueprint(bp)
    return flask_app


def test_bearer_missing_returns_401(tmp_openclaw_home: Path) -> None:
    key = "a" * 64
    app = _make_app_with_protected_route(key, tmp_openclaw_home)
    r = app.test_client().get("/api/protected")
    assert r.status_code == 401


def test_bearer_correct_returns_200(tmp_openclaw_home: Path) -> None:
    key = "a" * 64
    app = _make_app_with_protected_route(key, tmp_openclaw_home)
    r = app.test_client().get("/api/protected", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_bearer_wrong_eventually_429(tmp_openclaw_home: Path) -> None:
    key = "a" * 64
    app = _make_app_with_protected_route(key, tmp_openclaw_home)
    client = app.test_client()
    # 10 bad attempts — non-loopback IP via X-Forwarded-For trust requires
    # request.remote_addr to be loopback, so we set a fake non-whitelist remote
    # by mocking via environ.
    base_env = {
        "REMOTE_ADDR": "198.51.100.10",  # non-whitelisted public IP
    }
    for _ in range(MAX_AUTH_FAILURES):
        r = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer wrong"},
            environ_overrides=base_env,
        )
        assert r.status_code == 401
    r2 = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {key}"},
        environ_overrides=base_env,
    )
    assert r2.status_code == 429
    clear_auth_failures("198.51.100.10")


# -- Service unavailable when key missing ----------------------------------


def test_503_when_mgmt_key_missing(tmp_openclaw_home: Path) -> None:
    # Empty .env → no key configured.
    (tmp_openclaw_home / ".env").write_text("")
    from app import create_app

    flask_app = create_app({"TESTING": True})

    bp = Blueprint("test_503", __name__)

    @bp.route("/api/needs-key")
    @require_bearer
    def _route():  # type: ignore[no-untyped-def]
        return {"ok": True}

    flask_app.register_blueprint(bp)
    r = flask_app.test_client().get("/api/needs-key", headers={"Authorization": "Bearer x"})
    assert r.status_code == 503
