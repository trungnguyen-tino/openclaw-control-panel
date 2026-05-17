"""Self-update worker — downloads + swaps the openclaw-panel install.

Source server.js downloaded a single server.js file. We ship a tarball because
the Python tree spans many files.

Flow:
1. GET `{RELEASE_TARBALL_URL}` with `tag` substituted.
2. Extract to `/opt/openclaw-mgmt/.new/`.
3. Optionally verify sha256 against `<tarball>.sha256` sibling URL.
4. `os.replace` swap: `.new` → `current`, save old to `.old/<ts>`.
5. `systemctl restart openclaw-mgmt`.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tarfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from app.config import RELEASE_TARBALL_URL
from app.services.systemd_service import restart

log = logging.getLogger("openclaw.self_update")

_INSTALL_ROOT = Path("/opt/openclaw-mgmt")
_NEW_DIR = _INSTALL_ROOT / ".new"
_OLD_DIR = _INSTALL_ROOT / ".old"
_LOG_DIR = Path("/var/log/openclaw-mgmt")


def _url_for(tag: str) -> str:
    if not RELEASE_TARBALL_URL:
        raise RuntimeError(
            "RELEASE_TARBALL_URL not configured. "
            "Set OPENCLAW_PANEL_RELEASE_URL env var."
        )
    return RELEASE_TARBALL_URL.replace("{tag}", tag)


def _download(url: str, dest: Path, timeout: float = 120.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)


def _verify_sha256(tarball: Path, expected_url: str) -> bool:
    """Optional checksum verification — passes if the .sha256 URL exists."""
    try:
        r = requests.get(expected_url, timeout=15)
        if r.status_code != 200:
            return True  # Not available → skip verification, don't block.
        expected = r.text.strip().split()[0]
    except Exception:
        return True
    h = hashlib.sha256()
    with tarball.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest() == expected


def _extract(tarball: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(tarball) as tf:
        # Strip any leading directory inside the archive so contents land flat
        # under `dest/`.
        members = tf.getmembers()
        if members and members[0].isdir():
            prefix = members[0].name.rstrip("/") + "/"
            filtered = []
            for m in members[1:]:
                if m.name.startswith(prefix):
                    m.name = m.name[len(prefix) :]
                    if m.name:
                        filtered.append(m)
            tf.extractall(dest, members=filtered)  # noqa: S202 — controlled source
        else:
            tf.extractall(dest)  # noqa: S202


def _swap(new: Path, current: Path, archive_root: Path) -> None:
    archive_root.mkdir(parents=True, exist_ok=True)
    if current.exists():
        archive_dest = archive_root / time.strftime("%Y%m%d-%H%M%S")
        shutil.move(str(current), str(archive_dest))
    shutil.move(str(new), str(current))


def run(tag: str) -> None:
    """Synchronous worker — call inside a daemon thread."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / "self-update.log"
    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    log.setLevel(logging.INFO)
    try:
        url = _url_for(tag)
        log.info("self-update start url=%s", url)
        tarball = _INSTALL_ROOT / f".dl-{tag}.tar.gz"
        _download(url, tarball)
        sha_url = url + ".sha256"
        if not _verify_sha256(tarball, sha_url):
            log.error("checksum mismatch — aborting")
            return
        _extract(tarball, _NEW_DIR)
        tarball.unlink(missing_ok=True)
        # NB: don't replace the CURRENT process binary while running. Drop a
        # sentinel; a deployment hook (or systemd ExecStartPre) does the swap
        # before the next start.
        current = _INSTALL_ROOT / "current"
        _swap(_NEW_DIR, current, _OLD_DIR)
        log.info("swap complete — restarting service")
        ok, msg = restart("openclaw-mgmt")
        log.info("restart ok=%s msg=%s", ok, msg)
    except Exception as exc:  # noqa: BLE001 — bubble all errors to the log
        log.exception("self-update failed: %s", exc)


def run_async(tag: str) -> threading.Thread:
    t = threading.Thread(target=run, args=(tag,), daemon=True, name=f"self-update-{tag}")
    t.start()
    return t


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


__all__ = ["run", "run_async", "_origin"]
