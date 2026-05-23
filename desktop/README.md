# OpenClaw Desktop (Electron + WSL2)

Windows desktop wrapper for the OpenClaw Panel. Backend (Flask + openclaw npm)
runs inside a WSL2 Ubuntu-22.04 distro so we reuse 95% of the production VPS
code path. Electron only ships the Windows-side bridge.

## Architecture

```
Windows host
├── OpenClaw.exe (Electron main)
│   ├── Tray icon (Mở Panel / Settings / Thoát)
│   ├── BrowserWindow → http://127.0.0.1:9998
│   └── First-run wizard (BootstrapRunner)
│
└── WSL2 Ubuntu-22.04
    ├── openclaw-mgmt.service (Flask gunicorn :9998)
    ├── openclaw.service       (Node openclaw daemon :18789)
    └── caddy.service          (reverse proxy :80/:443 — optional)
```

WSL2 auto-forwards `localhost:9998` from the distro back to the Windows host,
so the Electron BrowserWindow talks to the backend over plain HTTP loopback —
no TLS or port mapping needed.

## Layout

```
desktop/
├── package.json              # electron + electron-builder config
├── src/
│   ├── main/
│   │   ├── index.js          # Electron entry: lifecycle, tray, IPC
│   │   ├── wsl-detector.js   # probe `wsl.exe --status` + distro list
│   │   ├── bootstrap-runner.js  # first-run orchestrator + events
│   │   └── preload-wizard.js    # contextBridge for the wizard UI
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

## Build (Windows installer)

```powershell
cd desktop
npm install
npm run build:win
# Output: dist/OpenClaw Setup <version>.exe (NSIS installer)
```

The installer is **unsigned** (per design choice — see commit history). End
users will see Windows SmartScreen warning on first install; click "More info
→ Run anyway".

## First-run flow

1. Wizard window opens, BootstrapRunner starts.
2. `wsl-detector.probe()` decides:
   - **READY** → skip straight to bootstrap.
   - **WSL_MISSING** → `wsl --install --no-distribution` → prompt user to reboot.
   - **DISTRO_MISSING** → `wsl --install -d Ubuntu-22.04`.
3. Provision distro: write `/etc/wsl.conf` so it boots as root (no
   interactive "create unix user" prompt).
4. Run `bootstrap.sh --domain 127.0.0.1` from the public GitHub Release
   inside the distro — `apt install` Node/Python/Caddy, `npm install -g
   openclaw@latest`, extract the panel tarball, and start the 3 systemd
   units (~5-10 min, progress streamed to wizard).
5. Healthcheck: `curl http://127.0.0.1:9998/api/health` from inside the
   distro → must return 200.
6. Settings flagged `bootstrapCompleted: true` → wizard closes, tray
   active, user can open the panel.

## Settings persistence

`%LOCALAPPDATA%\OpenClaw\settings.json`:

```json
{
  "autoStart": true,
  "openWindowOnStart": false,
  "bootstrapCompleted": true
}
```

`autoStart` writes the registry key via `app.setLoginItemSettings`.
Uninstall removes it.

## Phase roadmap

| Phase | Status |
| --- | --- |
| 0. WSL2 detector + bootstrap orchestrator | ✅ done |
| 1. Electron entry + tray + BrowserWindow | ✅ done |
| 2. First-run wizard UI polish | 🚧 minimal version exists |
| 3. Installer (electron-builder NSIS) | ⏸️ |
| 4. Auto-update via electron-updater | ⏸️ |
| 5. Win10/11 test matrix + error UX | ⏸️ |

## Not in scope for this wrapper

- **No TLS** — Electron→backend is loopback only.
- **No Caddy on Windows** — the WSL distro's Caddy still runs but is
  unused (Electron talks directly to gunicorn :9998).
- **No native Windows port** — `app/platform_paths.py` covers that
  abstraction for a future pivot, but Architecture B keeps every backend
  service inside the WSL Linux environment.
