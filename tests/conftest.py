"""pytest fixtures shared across phase test suites."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_openclaw_home(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolated /opt/openclaw tree per test — never touches host filesystem."""
    tmp = Path(tempfile.mkdtemp(prefix="openclaw-home-"))
    (tmp / "config" / "devices").mkdir(parents=True)
    (tmp / "config" / "agents").mkdir(parents=True)
    (tmp / ".openclaw").mkdir(parents=True)
    (tmp / ".env").write_text("")
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp))
    monkeypatch.setenv("OPENCLAW_TEMPLATES_DIR", str(tmp / "templates"))
    # Pin openclaw.json to the legacy config/ path used by test fixtures; the
    # production default is `<home>/.openclaw/openclaw.json` (see app.config).
    monkeypatch.setenv("OPENCLAW_CONFIG_FILE", str(tmp / "config" / "openclaw.json"))
    (tmp / "templates").mkdir()
    # Re-import config so PATHS picks up the new env (cached at import time).
    import app.config as cfg

    cfg.PATHS = cfg.Paths.from_env()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def app(tmp_openclaw_home: Path):
    """Flask app instance bound to an isolated home dir."""
    from app import create_app

    flask_app = create_app({"TESTING": True})
    flask_app.config["MGMT_API_KEY_TEST"] = "0" * 64
    yield flask_app


@pytest.fixture
def client(app):  # type: ignore[no-untyped-def]
    return app.test_client()


@pytest.fixture
def auth_header(monkeypatch: pytest.MonkeyPatch, tmp_openclaw_home: Path) -> dict[str, str]:
    """Seed .env with a known MGMT API key and return the matching Bearer header."""
    key = "f" * 64
    (tmp_openclaw_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture(autouse=True)
def _no_real_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt-and-braces: tests must NEVER shell out to real systemctl/journalctl.
    Individual tests opt in by stubbing run_cmd themselves.
    """
    if "ALLOW_REAL_SUBPROCESS" in os.environ:
        return
    # Sentinel only — actual stubbing happens per-test via monkeypatch of
    # app.utils.subprocess_safe.run_cmd. This fixture documents intent.
