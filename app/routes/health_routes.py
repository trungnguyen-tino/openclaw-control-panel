"""GET /api/health — unauthenticated liveness probe.

Used by install.sh post-install check and by oncall monitoring. Returns the
running version + uptime in seconds so dashboards can detect restarts.
"""

from __future__ import annotations

import time

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

VERSION = "1.0.0"
_BOOT_TS = time.time()


@health_bp.get("/api/health")
def health():  # type: ignore[no-untyped-def]
    return jsonify(
        {
            "ok": True,
            "version": VERSION,
            "uptimeSeconds": int(time.time() - _BOOT_TS),
        }
    )
