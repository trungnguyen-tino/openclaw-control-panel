"""`journalctl` tail wrapper, locked to the allowlisted services."""

from __future__ import annotations

from typing import Final

from app.config import ALLOWED_SERVICES
from app.utils.subprocess_safe import run_cmd

_JOURNALCTL: Final[str] = "/usr/bin/journalctl"
_DEFAULT_LINES = 100
_MAX_LINES = 1000


def tail(service: str, lines: int = _DEFAULT_LINES) -> list[str]:
    """Return last N lines from journalctl for `service`.

    Raises:
        ValueError: if service is not in the allowlist or lines is out of range.
    """
    if service not in ALLOWED_SERVICES:
        raise ValueError(f"Service '{service}' not in whitelist")
    if not isinstance(lines, int) or lines < 1 or lines > _MAX_LINES:
        raise ValueError(f"lines must be 1..{_MAX_LINES}")
    r = run_cmd(
        [_JOURNALCTL, "-u", service, "-n", str(lines), "--no-pager"],
        timeout=20,
    )
    if r.returncode != 0:
        return [r.stderr.strip()] if r.stderr else []
    return r.stdout.splitlines()
