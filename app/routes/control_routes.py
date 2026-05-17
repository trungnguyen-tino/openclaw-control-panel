"""Service-control endpoints: restart, stop, start, rebuild, upgrade, reset, self-update."""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from app import config as _cfg
from app.auth import require_bearer
from app.extensions import limiter
from app.services import self_update_service, systemd_service
from app.utils.dotenv_atomic import dotenv_set
from app.utils.subprocess_safe import run_cmd

log = logging.getLogger("openclaw.control")

control_bp = Blueprint("control", __name__, url_prefix="/api")

_UPGRADE_LOG = Path("/var/log/openclaw-mgmt/upgrade.log")
_UPGRADE_TIMEOUT_S = 5 * 60


def _service_response(ok: bool, msg: str, action: str) -> tuple[dict, int]:
    body = {"ok": ok, "action": action}
    if msg:
        body["message"] = msg
    return body, (200 if ok else 500)


@control_bp.post("/restart")
@limiter.limit("5 per minute")
@require_bearer
def post_restart():  # type: ignore[no-untyped-def]
    ok, msg = systemd_service.restart("openclaw")
    body, code = _service_response(ok, msg, "restart")
    return jsonify(body), code


@control_bp.post("/stop")
@limiter.limit("5 per minute")
@require_bearer
def post_stop():  # type: ignore[no-untyped-def]
    ok, msg = systemd_service.stop("openclaw")
    body, code = _service_response(ok, msg, "stop")
    return jsonify(body), code


@control_bp.post("/start")
@limiter.limit("5 per minute")
@require_bearer
def post_start():  # type: ignore[no-untyped-def]
    ok, msg = systemd_service.start("openclaw")
    body, code = _service_response(ok, msg, "start")
    return jsonify(body), code


@control_bp.post("/rebuild")
@limiter.limit("3 per minute")
@require_bearer
def post_rebuild():  # type: ignore[no-untyped-def]
    ok1, _ = systemd_service.restart("openclaw")
    ok2, _ = systemd_service.restart("caddy")
    ok = ok1 and ok2
    return (
        jsonify({"ok": ok, "action": "rebuild", "openclaw": ok1, "caddy": ok2}),
        200 if ok else 500,
    )


_VERSION_RE = re.compile(r"\b(\d+\.\d+\.\d+(?:-[A-Za-z0-9]+)?)\b")


def _detect_openclaw_version() -> str | None:
    """Parse `openclaw --version` → semver or None."""
    try:
        r = run_cmd(["/usr/bin/openclaw", "--version"], timeout=5)
        m = _VERSION_RE.search(r.stdout or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _run_upgrade_in_background(version: str = "latest") -> None:
    _UPGRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(_UPGRADE_LOG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(fh)
    try:
        pkg = f"openclaw@{version}"
        log.info("starting npm install -g %s", pkg)
        # `install` (not `update`) lets us pin a specific version. For "latest"
        # this still pulls the newest release.
        r = run_cmd(
            ["/usr/bin/npm", "install", "-g", pkg],
            timeout=_UPGRADE_TIMEOUT_S,
        )
        log.info("npm exit=%s stdout=%s", r.returncode, r.stdout[-1024:])
        if r.stderr:
            log.info("npm stderr=%s", r.stderr[-1024:])
        # Sync .env to the actual installed semver so openclaw Control UI sees
        # a real version (not the placeholder "latest" string).
        version = _detect_openclaw_version()
        if version:
            try:
                dotenv_set("OPENCLAW_VERSION", version)
                log.info("synced .env OPENCLAW_VERSION=%s", version)
            except Exception as e:  # noqa: BLE001
                log.warning("failed to sync .env version: %s", e)
        ok, msg = systemd_service.restart("openclaw")
        log.info("openclaw restart ok=%s msg=%s", ok, msg)
    except Exception as exc:  # noqa: BLE001
        log.exception("upgrade failed: %s", exc)


_VERSION_PATTERN = re.compile(r"^[0-9A-Za-z_.+\-]+$")


@control_bp.get("/upgrade/versions")
@limiter.limit("20 per hour")
@require_bearer
def get_upgrade_versions():  # type: ignore[no-untyped-def]
    """Return published openclaw npm versions newest-first, each flagged stable/beta.

    Beta = semver build metadata stripped, then any pre-release tag (contains "-").
    """
    try:
        r = run_cmd(
            ["/usr/bin/npm", "view", "openclaw", "versions", "--json"],
            timeout=15,
        )
        raw = json.loads(r.stdout or "[]")
        if not isinstance(raw, list):
            raw = [raw]
        # npm returns chronological ascending; reverse for newest-first.
        items = [
            {"version": v, "isBeta": "-" in v.split("+", 1)[0]}
            for v in reversed(raw)
        ]
        return jsonify({"ok": True, "versions": items})
    except Exception as exc:  # noqa: BLE001
        log.warning("upgrade versions probe failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc), "versions": []}), 500


@control_bp.post("/upgrade")
@limiter.limit("5 per hour")
@require_bearer
def post_upgrade():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    version = str(body.get("version", "latest")).strip() or "latest"
    if not _VERSION_PATTERN.match(version):
        return jsonify({"ok": False, "error": "invalid version"}), 400
    threading.Thread(
        target=_run_upgrade_in_background, args=(version,), daemon=True
    ).start()
    return (
        jsonify({"ok": True, "action": "upgrade", "started": True, "version": version}),
        202,
    )


@control_bp.post("/reset")
@limiter.limit("1 per hour")
@require_bearer
def post_reset():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    if body.get("confirm") != "RESET":
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Missing or wrong confirmation. Send {\"confirm\":\"RESET\"}.",
                }
            ),
            400,
        )
    config_dir = _cfg.PATHS.config_dir
    if config_dir.is_dir():
        for child in config_dir.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except FileNotFoundError:
                pass
    # Copy the bundled anthropic.json template if available.
    template = _cfg.PATHS.config_templates_dir / "anthropic.json"
    if template.is_file():
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(template, _cfg.PATHS.config_file)
    ok, msg = systemd_service.restart("openclaw")
    return jsonify({"ok": True, "action": "reset", "restart": ok, "message": msg}), 200


@control_bp.post("/self-update")
@limiter.limit("2 per hour")
@require_bearer
def post_self_update():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    tag = str(body.get("tag", "latest"))
    self_update_service.run_async(tag)
    return jsonify({"ok": True, "action": "self-update", "tag": tag, "async": True}), 202
