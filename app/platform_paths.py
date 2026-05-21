r"""OS-specific path + service abstraction.

Linux (production VPS): same behavior as before — ``/opt/openclaw{,-mgmt}/``,
systemd service control, Caddy reverse proxy in front.

Windows (Electron desktop): state under ``%LOCALAPPDATA%\OpenClaw\``, no
systemd (Electron main process is the supervisor), no Caddy (Flask binds
to 127.0.0.1 only and is loaded by Electron BrowserWindow).

The current production VPS code-path must keep producing the same ``Paths``
values as before — touching this file is allowed to add Windows support
but not to perturb the Linux defaults.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path


class OS(Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"  # dev-only; not a production target


def detect_os() -> OS:
    if sys.platform.startswith("win"):
        return OS.WINDOWS
    if sys.platform == "darwin":
        return OS.MACOS
    return OS.LINUX


def default_home() -> Path:
    """Where openclaw state lives — overridable via OPENCLAW_HOME env var.

    Honoured env var stays the FIRST check on every platform so existing
    deployments + tests keep working unchanged.
    """
    explicit = os.environ.get("OPENCLAW_HOME")
    if explicit:
        return Path(explicit)
    plat = detect_os()
    if plat is OS.LINUX:
        return Path("/opt/openclaw")
    if plat is OS.WINDOWS:
        # %LOCALAPPDATA%\OpenClaw — per-user, no admin needed, doesn't
        # sync to other PCs (which is correct for backend state).
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "OpenClaw"
        return Path.home() / "AppData" / "Local" / "OpenClaw"
    # macOS dev fallback — keep state under the user's home so it doesn't
    # need root or pollute /opt on a dev machine.
    return Path.home() / ".openclaw"


def default_templates_dir() -> Path:
    """Read-only provider templates (`*.json` shipped with the install)."""
    explicit = os.environ.get("OPENCLAW_TEMPLATES_DIR")
    if explicit:
        return Path(explicit)
    plat = detect_os()
    if plat is OS.LINUX:
        return Path("/etc/openclaw/config")
    if plat is OS.WINDOWS:
        # Bundled inside the Electron app resources directory at install time.
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        return Path(program_files) / "OpenClaw" / "resources" / "templates"
    return Path.home() / ".openclaw-templates"


def default_install_root() -> Path:
    """Where the panel itself is installed (read by self_update_service)."""
    explicit = os.environ.get("OPENCLAW_MGMT_ROOT")
    if explicit:
        return Path(explicit)
    plat = detect_os()
    if plat is OS.LINUX:
        return Path("/opt/openclaw-mgmt")
    if plat is OS.WINDOWS:
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        return Path(program_files) / "OpenClaw"
    return Path.home() / ".openclaw-mgmt"


def has_systemd() -> bool:
    """True only when running under a real systemd (Linux production VPS)."""
    return detect_os() is OS.LINUX and Path("/run/systemd/system").is_dir()
