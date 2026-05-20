"""Filesystem paths and runtime config constants.

Source parity: every path mirrors `_sources/vps-openclaw-management/management-api/server.js`
so existing state files (.env, openclaw.json, auth-profiles.json, devices) can be
dropped onto an openclaw-panel install without migration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    """All filesystem locations the management API reads/writes."""

    openclaw_home: Path
    env_file: Path
    config_dir: Path
    config_file: Path  # openclaw.json
    agents_dir: Path
    devices_dir: Path
    devices_pending: Path
    devices_paired: Path
    caddyfile: Path
    config_templates_dir: Path  # /etc/openclaw/config

    @classmethod
    def from_env(cls) -> Paths:
        home = Path(os.environ.get("OPENCLAW_HOME", "/opt/openclaw"))
        config_dir = home / "config"
        # Live openclaw runtime writes to .openclaw/openclaw.json — point the
        # panel at the same file so we don't fork the agents/channels/bindings
        # state. Env override allows tests/dev to use the legacy config/ dir.
        config_file_env = os.environ.get("OPENCLAW_CONFIG_FILE")
        config_file = (
            Path(config_file_env) if config_file_env else home / ".openclaw" / "openclaw.json"
        )
        devices_dir = config_dir / "devices"
        return cls(
            openclaw_home=home,
            env_file=home / ".env",
            config_dir=config_dir,
            config_file=config_file,
            agents_dir=config_dir / "agents",
            devices_dir=devices_dir,
            devices_pending=devices_dir / "pending.json",
            devices_paired=devices_dir / "paired.json",
            caddyfile=home / "Caddyfile",
            config_templates_dir=Path(
                os.environ.get("OPENCLAW_TEMPLATES_DIR", "/etc/openclaw/config")
            ),
        )


PATHS = Paths.from_env()

# OAuth Codex — matches source line 731 hardcoded client ID; env override
# allows ops to point at a different OpenAI client without code change.
OPENAI_CODEX_CLIENT_ID = os.environ.get(
    "OPENAI_CODEX_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann"
)
OPENAI_CODEX_ISSUER = os.environ.get("OPENAI_CODEX_ISSUER", "https://auth.openai.com")

# Rate-limit thresholds (matches source line 81-83).
MAX_AUTH_FAILURES = 10
BLOCK_DURATION_MS = 15 * 60 * 1000

# Release tarball URL template (filled when user has a GitLab/GitHub release).
# `{tag}` placeholder substituted at fetch time.
RELEASE_TARBALL_URL = os.environ.get(
    "OPENCLAW_PANEL_RELEASE_URL",
    "",  # empty until user publishes; self-update gracefully fails until set.
)

# Service whitelist for journalctl + control endpoints.
ALLOWED_SERVICES: frozenset[str] = frozenset({"openclaw", "caddy", "openclaw-mgmt"})

# CIDRs whose IPs bypass rate-limit (source server.js:87-93).
WHITELIST_CIDRS: tuple[str, ...] = (
    "127.0.0.1/32",
    "::1/128",
    "103.85.156.0/22",
    "103.234.20.0/22",
    "45.117.180.0/24",
)
