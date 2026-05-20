"""Allow-list for `/api/cli` and the SSE terminal stream.

Defense in depth:
1. Regex blocks any shell metacharacter — prevents quoting tricks.
2. shlex.split with posix=True (safe because metachars already rejected).
3. Tokens compared to a hardcoded ALLOWED_PREFIXES list. Only the leading N
   tokens of each prefix are matched; the rest are argv passthrough.
"""

from __future__ import annotations

import re
import shlex
from typing import Final

ALLOWED_PREFIXES: Final[tuple[tuple[str, ...], ...]] = (
    ("openclaw",),
    ("claw",),
    ("systemctl",),
    ("journalctl",),
    ("npm", "update", "-g", "openclaw"),
    ("df",),
    ("free",),
    ("uptime",),
    ("ps",),
    ("uname",),
    ("hostname",),
    ("date",),
)

# Metacharacters that enable shell escape — block before tokenization.
_META_RE = re.compile(r"[;&|`(){}!'\"<>$\\]")


# Public name predates the lint rule; renaming is a breaking API change.
class CliBlocked(Exception):  # noqa: N818
    """Raised when a command fails the whitelist."""


def parse(command: str) -> list[str]:
    if not command or not isinstance(command, str):
        raise CliBlocked("command required")
    if _META_RE.search(command):
        raise CliBlocked("shell metacharacter not allowed")
    try:
        parts = shlex.split(command, posix=True)
    except ValueError as e:
        raise CliBlocked(f"parse error: {e}") from e
    if not parts:
        raise CliBlocked("empty command")
    for prefix in ALLOWED_PREFIXES:
        if tuple(parts[: len(prefix)]) == prefix:
            return parts
    raise CliBlocked(f"'{parts[0]}' not in whitelist")
