"""System info (CPU, RAM, disk, OS, uptime) used by `/api/system`."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any

import psutil

from app.utils.subprocess_safe import run_cmd


def _get_primary_ip() -> str:
    """Best-effort detection of the outbound interface IP (no actual connection)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return socket.gethostbyname(socket.gethostname())


def _os_pretty_name() -> str:
    release = Path("/etc/os-release")
    if release.is_file():
        for raw in release.read_text(encoding="utf-8").splitlines():
            if raw.startswith("PRETTY_NAME="):
                return raw.split("=", 1)[1].strip().strip('"')
    return os.uname().sysname


def _node_version() -> str | None:
    try:
        r = run_cmd(["/usr/bin/node", "--version"], timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def _openclaw_version() -> str | None:
    try:
        r = run_cmd(["/usr/bin/openclaw", "--version"], timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


# CPU percent cache — `psutil.cpu_percent(interval=None)` returns delta since
# last call. First call always returns 0.0; cache value 2s to avoid blocking
# consecutive callers while still feeling live in the Topbar.
_cpu_cache: dict[str, float] = {"ts": 0.0, "val": 0.0}


def _cpu_pct() -> float:
    now = time.time()
    if now - _cpu_cache["ts"] < 2.0 and _cpu_cache["val"] > 0:
        return _cpu_cache["val"]
    val = psutil.cpu_percent(interval=None)
    if val > 0:
        _cpu_cache.update(ts=now, val=val)
    return val


def gather() -> dict[str, Any]:
    vmem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    loadavg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    cpu_pct = round(_cpu_pct(), 1)
    return {
        "hostname": socket.gethostname(),
        "ip": _get_primary_ip(),
        "os": _os_pretty_name(),
        "uptime": int(time.time() - psutil.boot_time()),
        "loadAvg": list(loadavg),
        "loadavg": list(loadavg),  # camelCase alias for v2 frontend
        "cpuPct": cpu_pct,
        "memory": {
            "total": int(vmem.total),
            "used": int(vmem.used),
            "available": int(vmem.available),
            "percent": float(vmem.percent),
        },
        "memUsed": int(vmem.used),
        "memTotal": int(vmem.total),
        "memPct": round(float(vmem.percent), 1),
        "disk": {
            "total": int(disk.total),
            "used": int(disk.used),
            "free": int(disk.free),
            "percent": float(disk.percent),
        },
        "diskUsed": int(disk.used),
        "diskTotal": int(disk.total),
        "diskPct": round(float(disk.percent), 1),
        "nodeVersion": _node_version(),
        "openclawVersion": _openclaw_version(),
    }
