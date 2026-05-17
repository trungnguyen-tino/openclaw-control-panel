"""Singleton thread that polls pending.json every 5s for 60s after /pair."""

from __future__ import annotations

import logging
import threading
import time
from typing import Final

from app.services import devices_service

log = logging.getLogger("openclaw.pairing")

POLL_INTERVAL_S: Final[float] = 5.0
WINDOW_MS: Final[int] = 60 * 1000


class PairingPoller:
    def __init__(self) -> None:
        self._active_until_ms: int = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def is_active(self) -> bool:
        return self._now_ms() < self._active_until_ms

    def activate(self) -> None:
        with self._lock:
            self._active_until_ms = self._now_ms() + WINDOW_MS
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._loop, daemon=True, name="pairing-poller"
                )
                self._thread.start()
                log.info("pairing poller activated (60s window)")

    def _loop(self) -> None:
        while self._now_ms() < self._active_until_ms:
            try:
                devices_service.approve_all_pending()
            except Exception as exc:  # noqa: BLE001
                log.exception("approve_all_pending failed: %s", exc)
            time.sleep(POLL_INTERVAL_S)
        log.info("pairing poller window expired")


_poller = PairingPoller()


def get_poller() -> PairingPoller:
    return _poller
