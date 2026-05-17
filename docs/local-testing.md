# Local testing with docker-compose

This stack runs the panel locally without a real VPS. It includes:

- **mgmt** — the Python Flask + gunicorn management API + bundled SPA
- **caddy** — reverse proxy with self-signed cert (TLS `internal`)
- **openclaw** — placeholder nginx serving a "stub" page on :18789 (the real `openclaw` npm package is too heavy for a dev stack)

`systemctl` and `journalctl` are replaced inside the mgmt container with mock scripts so the dashboard reports `active` and `/api/logs` returns synthetic lines.

## Prerequisites

- Docker 24+ with the `compose` plugin.
- Repo cloned + `cd ui && npm install && npm run build` once (produces `static/dist/`).

## Run

```bash
cd ui && npm run build   # only needed when SPA source changes
cd ..
docker compose -f docker/compose.yaml up --build
```

First boot pulls images + builds the mgmt image (≈30s on a warm cache).

## Open

| URL | What loads |
|-----|------------|
| <https://localhost/> | SPA login page (accept the self-signed cert warning) |
| <http://localhost:9998/> | Same SPA, bypassing Caddy |
| <https://localhost/gateway/> | The openclaw stub page |
| <http://localhost:9998/api/health> | JSON health probe |

## Sign in

Two options:

1. **Paste API key** — use the placeholder from `docker/.env.compose`:
   `devmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmg`
2. **Username + password** — first call `POST /api/auth/create-user` with the Bearer above to seed credentials, then log in via the form.

Curl example to seed an admin:

```bash
KEY=devmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmgmtkeydevmg
curl -k -X POST https://localhost/api/auth/create-user \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"hunter2"}'
```

## What works in this stack

- Login / logout (key paste + username/password flows)
- Dashboard cards (memory + disk via psutil from inside the container; CPU loadavg = container loadavg)
- Provider switching (writes `/opt/openclaw/config/openclaw.json` inside the mgmt container volume)
- Custom provider CRUD
- Agents + bindings + channels CRUD
- Devices: pair URL `https://localhost/pair?token=<gateway>` activates the 60s poller; pending → paired round-trip works
- `/api/logs` + `/api/logs/stream` (SSE) → synthetic mock output
- `/api/terminal/stream` → runs against the mock shims (e.g., `systemctl status openclaw`)
- Domain change (writes Caddyfile inside container — won't reflect in real Caddy without manual restart)
- Env editor (with locked-key protection)

## What does NOT work locally

- Real `openclaw gateway` — the stub answers `/gateway/*` with a static page only.
- Real systemd → service restarts are no-ops; `/api/restart` reports success but nothing changes.
- Let's Encrypt TLS — Caddy uses `tls internal` (self-signed).
- ChatGPT Codex OAuth → networks to api.openai.com but our refresher is disabled (`OPENCLAW_DISABLE_REFRESHER=1`).

## Teardown

```bash
docker compose -f docker/compose.yaml down       # keeps volumes (state preserved)
docker compose -f docker/compose.yaml down -v    # purges volumes
```

## Customizing the dev creds

Edit `docker/.env.compose`. Replace the placeholder tokens with `openssl rand -hex 32`. They are not real secrets but `.env.compose` is git-ignored by the repo's `.gitignore` pattern `.env*`.

## Caveats

- The mock `systemctl` always reports `active`. Don't trust the dashboard's "services up" reading.
- Persistent state lives in the named volume `openclaw-state` — `docker volume rm openclaw-panel_openclaw-state` to reset.
- The container runs as root (matches production layout); for true dev, drop privileges via a `user:` directive in `compose.yaml`.
