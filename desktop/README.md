# OpenClaw Desktop (Electron — Linux + Windows)

Cross-platform desktop wrapper for the OpenClaw Panel. One Electron app
that runs on Ubuntu Desktop **and** Windows, plus an optional one-click
Cloudflare Quick Tunnel for remote access.

## Architecture

```
┌─ OpenClaw.exe / openclaw (Electron main) ─────────────────────────────┐
│                                                                       │
│  Platform-aware bootstrap (auto-detect at launch):                    │
│    Linux  → pkexec bash -c 'curl bootstrap.sh | bash -- --domain 127.0.0.1' │
│    Win32  → wsl --install Ubuntu-22.04 → run bootstrap.sh inside     │
│                                                                       │
│  Tray menu:                                                           │
│    ├─ Mở Panel        → BrowserWindow → http://127.0.0.1:9998        │
│    ├─ URL từ xa       → cloudflared tunnel --url 127.0.0.1:9998      │
│    │                    → https://<random>.trycloudflare.com         │
│    ├─ Khởi động cùng máy   (toggle)                                  │
│    ├─ Mở cửa sổ khi start  (toggle)                                  │
│    └─ Thoát                                                           │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
            │
            ▼
   Backend (same code on both platforms; runs natively on Ubuntu, inside
   WSL2 on Windows):
     openclaw-mgmt.service  (Flask gunicorn :9998)
     openclaw.service       (Node openclaw daemon :18789)
     caddy.service          (dormant — Electron talks to :9998 direct)
```

On Windows, WSL2 auto-forwards `localhost:9998` to the Windows host so
the Electron BrowserWindow + Cloudflare tunnel both reach the backend
over plain HTTP loopback — no TLS, no port mapping.

## Remote access via Cloudflare Quick Tunnel

The tray menu has an opt-in **"Bật URL từ xa"** button. Click it and:

1. `cloudflared` binary downloads to `~/.local/share/OpenClaw/bin/` on
   first use (or `%LOCALAPPDATA%\OpenClaw\bin\` on Windows).
2. `cloudflared tunnel --url http://127.0.0.1:9998` spawns.
3. Within ~5 seconds the tray label flips to
   `URL từ xa: https://<random>.trycloudflare.com` — click to open or
   copy to clipboard.
4. Tunnel stays alive until the user clicks **"Tắt URL từ xa"** or
   quits the app.

Default is **opt-in** for privacy — the panel is never exposed to the
internet unless the user explicitly asks. Quick Tunnel URLs are
ephemeral (regenerated on each restart); for a permanent URL with a
custom domain, a future "Bring your own Cloudflare account" advanced
setting will switch to Named Tunnel mode.

## Layout

```
desktop/
├── package.json              # electron + electron-builder config (Linux + Win)
├── src/
│   ├── main/
│   │   ├── index.js                # Electron entry: lifecycle, tray, IPC
│   │   ├── wsl-detector.js         # Windows-only: probe wsl.exe
│   │   ├── bootstrap-runner.js     # cross-platform first-run orchestrator
│   │   ├── cloudflared-manager.js  # download + spawn Quick Tunnel
│   │   └── preload-wizard.js       # contextBridge for the wizard UI
│   └── wizard/
│       └── index.html        # first-run progress UI
└── resources/                # icons, bundled assets (TBD)
```

First-run pulls `bootstrap.sh` from the public GitHub Release inside the
WSL distro — `bash -c 'curl … | bash -s -- --domain 127.0.0.1'`. That
wraps the same `install.sh` the VPSes use, so Node 24 + openclaw npm +
Python 3.12 + Caddy + the 3 systemd services land in the distro from
scratch (~5-10 min on first launch).

## Development

```powershell
# On a Windows host
cd desktop
npm install
npm start
```

To smoke-test the WSL detector without launching Electron:

```powershell
node src/main/wsl-detector.js
```

It prints a JSON verdict and exits 0/1 depending on whether WSL2 + the
required distro are ready.

## Build

```bash
cd desktop
npm install

# Windows installer (.exe NSIS)
npm run build:win
# Output: dist/OpenClaw Setup <version>.exe

# Ubuntu installer (.deb + AppImage)
npm run build:linux
# Output: dist/openclaw-desktop_<version>_amd64.deb
#         dist/OpenClaw-<version>.AppImage
```

Both installers are **unsigned**. End users will see:
- Windows: SmartScreen warning on first install → click "More info → Run anyway"
- Ubuntu: no warning, but `.deb` install needs `sudo dpkg -i`

## First-run flow

Step 0 (both platforms): probe `http://127.0.0.1:9998/api/health` —
if reachable, the panel is already installed (manual VPS-style install
or a prior successful first-run), skip everything and go to tray mode.

### Linux branch

1. `pkexec` opens the desktop's polkit password dialog (system GUI prompt).
2. User authenticates → script runs as root.
3. `curl bootstrap.sh | bash -s -- --domain 127.0.0.1` — apt-install
   Node 24 / Python 3.12 / Caddy 2, `npm install -g openclaw@latest`,
   extract the panel tarball, write & start 3 systemd units (~5-10 min,
   progress streamed to wizard).
4. Healthcheck on :9998 → must return 200.

### Windows branch

1. `wsl-detector.probe()` decides:
   - **READY** → skip straight to bootstrap.
   - **WSL_MISSING** → `wsl --install --no-distribution` → prompt user to reboot.
   - **DISTRO_MISSING** → `wsl --install -d Ubuntu-22.04`.
2. Provision distro: write `/etc/wsl.conf` so it boots as root (no
   interactive "create unix user" prompt).
3. Run `bootstrap.sh --domain 127.0.0.1` from the public GitHub Release
   inside the distro (same install path as Linux, just one extra hop).
4. Healthcheck through the distro on :9998 → must return 200.

After either branch, settings flag `bootstrapCompleted: true`, wizard
closes, tray icon active.

## Settings persistence

Stored at `app.getPath("userData")`:
- Windows: `%LOCALAPPDATA%\OpenClaw\settings.json`
- Linux:   `~/.config/OpenClaw/settings.json`

```json
{
  "autoStart": true,
  "openWindowOnStart": false,
  "bootstrapCompleted": true
}
```

`autoStart` is wired via `app.setLoginItemSettings`:
- Windows: writes the `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` key.
- Linux: drops a `.desktop` autostart entry into `~/.config/autostart/`.

Uninstalling the app removes both.

## Phase roadmap

| Phase | Status |
| --- | --- |
| 0. WSL2 detector + bootstrap orchestrator (Win) | ✅ done |
| 0.5 Linux pkexec branch + healthcheck short-circuit | ✅ done |
| 1. Electron entry + tray + BrowserWindow | ✅ done |
| 1.5 Cloudflare Quick Tunnel manager + tray UI | ✅ done |
| 2. First-run wizard UI polish | 🚧 minimal version exists |
| 3. Installer (electron-builder NSIS + deb + AppImage) | ⏸️ |
| 4. Auto-update via electron-updater | ⏸️ |
| 5. Linux + Windows test matrix + error UX | ⏸️ |
| 6. Optional: Named Tunnel mode (bring-own-CF-account) | ⏸️ |

## Not in scope for this wrapper

- **No TLS for local panel** — Electron→backend is loopback only.
  Cloudflare Tunnel handles TLS for the remote URL.
- **No Caddy proxy use on desktop** — Caddy still installs but stays
  dormant on :80/:443; the Electron BrowserWindow + cloudflared both
  talk directly to gunicorn :9998.
- **No native Windows backend port** — `app/platform_paths.py` covers
  that abstraction for a future pivot, but Architecture B keeps every
  backend service inside a Linux environment (host on Ubuntu, WSL2 on
  Windows).
- **Named Tunnel** with custom domain requires a Cloudflare account and
  is out of scope for the default flow. A future advanced setting will
  switch from Quick Tunnel to Named Tunnel by accepting a CF API token.
