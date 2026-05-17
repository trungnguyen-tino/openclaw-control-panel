"""Safe subprocess wrapper.

Hard guarantees:
- args MUST be a list (no shell strings) → shell=False always.
- env scrubbed to a small allowlist; caller may add extra vars explicitly.
- timeout-bounded by default.

Used by systemd_service, journalctl_service, provider key tests, CLI proxy.
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404  (intentional — entire module exists to harden it)
from collections.abc import Sequence
from typing import Final

_ENV_ALLOWLIST: Final[tuple[str, ...]] = ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
_DEFAULT_PATH: Final[str] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _scrub_env(extra: dict[str, str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    for k in _ENV_ALLOWLIST:
        if k in os.environ:
            env[k] = os.environ[k]
    env.setdefault("PATH", _DEFAULT_PATH)
    if extra:
        env.update(extra)
    return env


def run_cmd(
    args: Sequence[str],
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    input: str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command safely.

    Raises:
        TypeError: if `args` is not a list/tuple (defense-in-depth).
        subprocess.TimeoutExpired: if process exceeds `timeout`.
        subprocess.CalledProcessError: if `check=True` and exit != 0.
    """
    if not isinstance(args, (list, tuple)):
        raise TypeError(f"run_cmd requires list/tuple of args, got {type(args).__name__}")
    return subprocess.run(  # noqa: S603 — args validated; shell=False
        list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_scrub_env(env),
        cwd=cwd,
        input=input,
        check=check,
        shell=False,
    )
