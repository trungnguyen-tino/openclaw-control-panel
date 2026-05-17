"""SSE generator that streams whitelisted shell output to the browser."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from collections.abc import Iterator

log = logging.getLogger("openclaw.terminal")

_DEFAULT_TIMEOUT_S = 300
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
_DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _scrubbed_env() -> dict[str, str]:
    import os

    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env.setdefault("PATH", _DEFAULT_PATH)
    return env


def _sse(event: str | None, data: dict) -> str:
    payload = f"data: {json.dumps(data)}\n\n"
    if event:
        return f"event: {event}\n{payload}"
    return payload


def stream_journalctl(service: str, timeout: float = _DEFAULT_TIMEOUT_S) -> Iterator[str]:
    """Live `journalctl -u <service> -f` SSE stream for the logs page."""
    parts = ["/usr/bin/journalctl", "-u", service, "-f", "--no-pager", "-n", "100"]
    yield from stream_command(parts, timeout=timeout)


def stream_command(parts: list[str], timeout: float = _DEFAULT_TIMEOUT_S) -> Iterator[str]:
    """Yield SSE-formatted lines from `parts` execution. Caller wraps with
    `flask.stream_with_context`. Always closes with an `end` event."""
    yield _sse("start", {"cmd": parts})
    proc = subprocess.Popen(  # noqa: S603 — caller validates args
        parts,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=_scrubbed_env(),
        shell=False,
        text=True,
        bufsize=1,
    )
    started = time.time()
    try:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            if time.time() - started > timeout:
                proc.kill()
                yield _sse("error", {"reason": "timeout", "elapsed": int(time.time() - started)})
                break
            yield _sse(None, {"line": line.rstrip("\n")})
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log.warning("subprocess refused to die: %s", parts)
    yield _sse("end", {"exitCode": proc.returncode})
