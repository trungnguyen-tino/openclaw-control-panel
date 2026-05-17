"""Domain-change pipeline with full rollback."""

from __future__ import annotations

import logging
import re
import socket
import time
from typing import Any

import requests

from app.services import caddy_service, dns_check_service, systemd_service
from app.utils.dotenv_atomic import dotenv_read, dotenv_set

log = logging.getLogger("openclaw.domain_change")

DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)


def server_public_ip() -> str | None:
    try:
        r = requests.get("https://api.ipify.org", timeout=5)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except requests.RequestException:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return None


def change_domain(new_domain: str, force_skip_dns: bool = False) -> dict[str, Any]:
    new_domain = new_domain.strip().lower()
    if not DOMAIN_RE.match(new_domain):
        return {"ok": False, "error": "Invalid domain format"}
    backup_env = dotenv_read()
    cf_path = caddy_service.caddyfile_path()
    caddyfile_backup = cf_path.read_bytes() if cf_path.is_file() else b""
    resolved = None if force_skip_dns else dns_check_service.resolve_a(new_domain)
    public_ip = server_public_ip()
    # Source heuristic: DNS resolves to server's IP → Let's Encrypt; else self-signed.
    tls = "" if (resolved and public_ip and resolved == public_ip) else "tls internal"
    try:
        dotenv_set("DOMAIN", new_domain)
        dotenv_set("CADDY_TLS", tls)
        caddy_service.render_and_write()
        ok, msg = caddy_service.restart()
        if not ok:
            raise RuntimeError(f"caddy restart failed: {msg}")
        time.sleep(1)
        if not caddy_service.is_active():
            raise RuntimeError("caddy not active after restart")
        return {
            "ok": True,
            "domain": new_domain,
            "ssl": "letsencrypt" if not tls else "self-signed",
            "resolved": resolved,
            "publicIp": public_ip,
        }
    except Exception as e:
        log.exception("domain change failed, rolling back: %s", e)
        # rollback env
        for k, v in backup_env.items():
            dotenv_set(k, v)
        if caddyfile_backup:
            cf_path.write_bytes(caddyfile_backup)
        systemd_service.restart("caddy")
        return {"ok": False, "error": str(e), "rolledBack": True}
