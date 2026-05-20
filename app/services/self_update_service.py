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
from app.services.systemd_service import restart_detached

log = logging.getLogger("openclaw.self_update")

_INSTALL_ROOT = Path("/opt/openclaw-mgmt")
_NEW_DIR = _INSTALL_ROOT / ".new"
_OLD_DIR = _INSTALL_ROOT / ".old"
_LOG_DIR = Path("/var/log/openclaw-mgmt")
_OPENCLAW_HOME = Path("/opt/openclaw")
_SYSTEMD_DIR = Path("/etc/systemd/system")
_USR_LOCAL_BIN = Path("/usr/local/bin")


def _url_for(tag: str) -> str:
    if not RELEASE_TARBALL_URL:
        raise RuntimeError(
            "RELEASE_TARBALL_URL not configured. "
            "Set OPENCLAW_PANEL_RELEASE_URL env var."
        )
    # GitHub's "latest" alias uses a different URL shape:
    # releases/latest/download/<asset> instead of releases/download/<tag>/<asset>.
    if tag == "latest":
        return RELEASE_TARBALL_URL.replace(
            "/releases/download/{tag}/", "/releases/latest/download/"
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
    _promote_to_live(current)


# Top-level entries that live under /opt/openclaw-mgmt/ but must NOT be
# overwritten by promotion (runtime/venv state, archive dirs, the staged tree
# itself, and on-disk backups).
_PROMOTE_SKIP: frozenset[str] = frozenset(
    {".venv", "current", ".new", ".old"}
)


def _promote_to_live(staged: Path) -> None:
    """Copy `staged/*` on top of `_INSTALL_ROOT` so gunicorn reloads new code.

    The previous design left `staged/` as a side-tree and relied on a non-
    existent ExecStartPre hook. Promotion fixes that: every file under the
    staged tree is copied into the live root, skipping runtime entries
    (`.venv`, archive dirs, the staged tree itself, and on-disk backups).
    """
    if not staged.is_dir():
        return
    for entry in staged.iterdir():
        if entry.name in _PROMOTE_SKIP or entry.name.startswith(".live-backup-"):
            continue
        dst = _INSTALL_ROOT / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, dst)


def _copy_if_different(src: Path, dst: Path, mode: int = 0o644) -> bool:
    """Copy `src` → `dst` only if content differs. Returns True if copied."""
    if not src.exists():
        return False
    if dst.exists() and src.read_bytes() == dst.read_bytes():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    dst.chmod(mode)
    return True


def migrate_infra(staged: Path) -> dict[str, bool]:
    """Retro-fix legacy VPS infra on every self-update.

    Re-applies files outside `/opt/openclaw-mgmt/` that bug-fix releases need
    to land on existing VPS (not just fresh installs). Each step is idempotent
    via content compare — no-op when already current.

    Surfaces migrated:
      - /opt/openclaw/Caddyfile             ← app/caddy/Caddyfile.template
      - /etc/systemd/system/caddy.service.d/override.conf
      - /etc/systemd/system/openclaw-healthcheck.{service,timer}
      - /usr/local/bin/openclaw-healthcheck.sh
      - /usr/local/bin/openclaw-sync-auth-profiles.sh
      - /usr/local/bin/openclaw-config-enforce.sh

    Caller must run systemctl daemon-reload + reload caddy after if changes!=0.
    Returns dict of {filename: changed?} for logging.
    """
    changed: dict[str, bool] = {}
    # 1. Caddyfile — preserve user customisations if they marked the file with
    # `# panel-managed: false` comment, else overwrite.
    caddyfile_dst = _OPENCLAW_HOME / "Caddyfile"
    caddyfile_src = staged / "app" / "caddy" / "Caddyfile.template"
    if caddyfile_dst.exists() and "# panel-managed: false" in caddyfile_dst.read_text(
        encoding="utf-8", errors="replace"
    ):
        log.info("Caddyfile has 'panel-managed: false' marker — skipping")
        changed["Caddyfile"] = False
    else:
        # Back up before overwrite — first time, keep a recovery copy.
        if caddyfile_dst.exists():
            backup = caddyfile_dst.with_suffix(".bak-pre-migrate")
            if not backup.exists():
                shutil.copy2(caddyfile_dst, backup)
        changed["Caddyfile"] = _copy_if_different(caddyfile_src, caddyfile_dst, 0o644)

    # 2. Systemd drop-ins.
    for unit in ("caddy-override.conf",):
        src = staged / "systemd" / unit
        dst = _SYSTEMD_DIR / "caddy.service.d" / "override.conf"
        changed[f"systemd/{unit}"] = _copy_if_different(src, dst, 0o644)

    # 3. Healthcheck timer + service.
    for unit in ("openclaw-healthcheck.service", "openclaw-healthcheck.timer"):
        src = staged / "systemd" / unit
        dst = _SYSTEMD_DIR / unit
        changed[f"systemd/{unit}"] = _copy_if_different(src, dst, 0o644)

    # 4. Helper scripts (executable).
    for script in (
        "openclaw-healthcheck.sh",
        "openclaw-sync-auth-profiles.sh",
        "openclaw-config-enforce.sh",
    ):
        src = staged / "scripts" / script
        dst = _USR_LOCAL_BIN / script
        changed[f"scripts/{script}"] = _copy_if_different(src, dst, 0o755)

    return changed


def _validate_invariants() -> list[str]:
    """Check post-migrate invariants. Returns list of failure messages."""
    failures: list[str] = []
    caddyfile = _OPENCLAW_HOME / "Caddyfile"
    if caddyfile.exists():
        content = caddyfile.read_text(encoding="utf-8", errors="replace")
        if "auto_https disable_redirects" not in content:
            failures.append("Caddyfile missing 'auto_https disable_redirects' block")
        if "/gw" not in content:
            failures.append("Caddyfile missing /gw route")
    auth_py = _INSTALL_ROOT / "app" / "auth.py"
    if auth_py.exists():
        if 'request.args.get("auth")' not in auth_py.read_text(encoding="utf-8"):
            failures.append("auth.py missing ?auth= query fallback (SSE will 401)")
    return failures


def run(tag: str) -> None:
    """Synchronous worker — call inside a daemon thread."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / "self-update.log"
    # Avoid handler accumulation across repeated `run()` calls in the same
    # process — each call previously added a new FileHandler, causing every
    # log line to be written N times.
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(log_file)
        for h in log.handlers
    ):
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
        # Migrate infra (Caddyfile, systemd, scripts) from the staged tree
        # BEFORE we move it on top of /opt/openclaw-mgmt/. Reads from .new/,
        # writes to /opt/openclaw/, /etc/systemd/, /usr/local/bin/.
        migrated = migrate_infra(_NEW_DIR)
        changed_count = sum(1 for v in migrated.values() if v)
        log.info("infra migration: changed=%d details=%s", changed_count, migrated)
        if changed_count:
            # Reload caddy + daemon-reload happen via subprocess; safe to skip
            # errors so a stale caddy doesn't block the panel update.
            import subprocess

            subprocess.run(["systemctl", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "reload-or-restart", "caddy"], check=False)
            log.info("caddy reloaded after infra migration")
        # NB: don't replace the CURRENT process binary while running. Drop a
        # sentinel; a deployment hook (or systemd ExecStartPre) does the swap
        # before the next start.
        current = _INSTALL_ROOT / "current"
        _swap(_NEW_DIR, current, _OLD_DIR)
        failures = _validate_invariants()
        if failures:
            log.warning("post-update invariants failed: %s", failures)
        else:
            log.info("post-update invariants OK")
        log.info("swap complete — restarting service (detached)")
        ok, msg = restart_detached("openclaw-mgmt")
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
