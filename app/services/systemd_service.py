"""Wrappers around `systemctl` for the openclaw, caddy, openclaw-mgmt units."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from app.config import ALLOWED_SERVICES
from app.utils.subprocess_safe import run_cmd

_SYSTEMCTL: Final[str] = "/usr/bin/systemctl"


def _assert_allowed(name: str) -> None:
    if name not in ALLOWED_SERVICES:
        raise ValueError(f"Service '{name}' not in whitelist")


def is_active(name: str) -> bool:
    _assert_allowed(name)
    r = run_cmd([_SYSTEMCTL, "is-active", name], timeout=5)
    return r.stdout.strip() == "active"


def status_str(name: str) -> str:
    _assert_allowed(name)
    r = run_cmd([_SYSTEMCTL, "is-active", name], timeout=5)
    return r.stdout.strip() or "unknown"


def restart(name: str) -> tuple[bool, str]:
    _assert_allowed(name)
    r = run_cmd([_SYSTEMCTL, "restart", name], timeout=30)
    ok = r.returncode == 0
    return ok, (r.stderr or r.stdout).strip()


def stop(name: str) -> tuple[bool, str]:
    _assert_allowed(name)
    r = run_cmd([_SYSTEMCTL, "stop", name], timeout=30)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def start(name: str) -> tuple[bool, str]:
    _assert_allowed(name)
    r = run_cmd([_SYSTEMCTL, "start", name], timeout=30)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def started_at(name: str) -> datetime | None:
    """Parse `ActiveEnterTimestamp` → datetime. Returns None if not active."""
    _assert_allowed(name)
    r = run_cmd(
        [_SYSTEMCTL, "show", "-p", "ActiveEnterTimestamp", name],
        timeout=5,
    )
    if r.returncode != 0:
        return None
    line = r.stdout.strip()
    if "=" not in line:
        return None
    _, _, value = line.partition("=")
    value = value.strip()
    if not value or value == "0":
        return None
    # Format: "Mon 2026-05-13 03:00:01 UTC"
    for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
