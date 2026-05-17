"""Caddyfile rendering + atomic write + restart wrapper."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from app import config as _cfg
from app.services import systemd_service

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "caddy" / "Caddyfile.template"
_CADDY_MODE = 0o644
_WRITE_LOCK = threading.Lock()


def caddyfile_path() -> Path:
    return _cfg.PATHS.caddyfile


def render_template() -> str:
    """Return the static template — Caddy resolves $DOMAIN/$CADDY_TLS at runtime."""
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Caddyfile template missing: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def write_atomic(content: str) -> None:
    p = caddyfile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp = tempfile.mkstemp(prefix=".Caddyfile.", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, _CADDY_MODE)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise


def restart() -> tuple[bool, str]:
    return systemd_service.restart("caddy")


def is_active() -> bool:
    return systemd_service.is_active("caddy")


def render_and_write() -> None:
    write_atomic(render_template())
