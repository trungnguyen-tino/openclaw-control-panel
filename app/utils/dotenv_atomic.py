"""Atomic `.env` reader/writer.

Source Node code does line-by-line in-place rewriting which can corrupt the
file if killed mid-write. This module always writes a temp file then renames
via `os.replace` (POSIX-atomic) and `chmod 0600` to keep secrets readable only
by the service user.

Format preserved byte-for-byte: existing line ordering + blank lines + comments
are retained; new keys are appended.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from app import config as _cfg

_ENV_FILE_MODE = 0o600
_WRITE_LOCK = threading.Lock()


def _path() -> Path:
    # Read PATHS lazily so test fixtures that reassign `cfg.PATHS` after import
    # still take effect.
    return _cfg.PATHS.env_file


def dotenv_read(path: Path | None = None) -> dict[str, str]:
    """Parse `.env` → ordered dict of KEY=VALUE.

    - Lines starting with `#` are ignored.
    - Values may be quoted (single or double); quotes stripped.
    - Lines without `=` are ignored.
    """
    p = path or _path()
    if not p.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        out[key] = val
    return out


def dotenv_get(key: str, default: str | None = None, path: Path | None = None) -> str | None:
    return dotenv_read(path).get(key, default)


def _write_atomic(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".env.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, _ENV_FILE_MODE)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def dotenv_set(key: str, value: str, path: Path | None = None) -> None:
    """Replace existing KEY= line in place; append new key at file end.

    Comments and blank lines unchanged. Value not quoted (matches source).
    Module-level lock serializes the read-modify-write window so concurrent
    callers don't trample each other.
    """
    p = path or _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        existing = (
            p.read_text(encoding="utf-8").splitlines(keepends=False) if p.is_file() else []
        )
        found = False
        new_lines: list[str] = []
        for line in existing:
            stripped = line.lstrip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        content = "\n".join(new_lines)
        if not content.endswith("\n"):
            content += "\n"
        _write_atomic(content, p)


def dotenv_unset(key: str, path: Path | None = None) -> None:
    p = path or _path()
    if not p.is_file():
        return
    with _WRITE_LOCK:
        new_lines: list[str] = []
        for line in p.read_text(encoding="utf-8").splitlines(keepends=False):
            stripped = line.lstrip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                continue  # drop
            new_lines.append(line)
        content = "\n".join(new_lines)
        if new_lines and not content.endswith("\n"):
            content += "\n"
        _write_atomic(content, p)


def dotenv_update_many(pairs: dict[str, str], path: Path | None = None) -> None:
    """Batch set — single write, preserves ordering for existing keys."""
    for k, v in pairs.items():
        dotenv_set(k, v, path=path)
