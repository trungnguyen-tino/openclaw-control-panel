"""Daemon thread that refreshes expiring OAuth tokens across all agents."""

from __future__ import annotations

import logging
import threading
import time

from app.services import oauth_codex_service

log = logging.getLogger("openclaw.oauth_refresher")

REFRESH_TICK_S = 60
REFRESH_LEAD_TIME_MS = 10 * 60 * 1000  # refresh if <10 min remaining

_started = False
_started_lock = threading.Lock()


def _loop_body() -> None:
    try:
        oauth_codex_service._store.gc()  # type: ignore[attr-defined]
        now_ms = int(time.time() * 1000)
        for agent_id, key, prof in oauth_codex_service.list_oauth_profiles_for_all_agents():
            if prof.get("dead"):
                continue
            expires = int(prof.get("expires", 0))
            if expires - now_ms < REFRESH_LEAD_TIME_MS:
                oauth_codex_service.refresh_profile(agent_id, key)
    except Exception as exc:  # noqa: BLE001 — keep loop alive
        log.exception("refresher tick failed: %s", exc)


def _loop() -> None:
    log.info("oauth refresher thread started tick=%ds", REFRESH_TICK_S)
    while True:
        _loop_body()
        time.sleep(REFRESH_TICK_S)


def start_once() -> None:
    """Idempotent — multiple `create_app` calls won't spawn duplicate threads."""
    global _started
    with _started_lock:
        if _started:
            return
        t = threading.Thread(target=_loop, daemon=True, name="oauth-refresher")
        t.start()
        _started = True
