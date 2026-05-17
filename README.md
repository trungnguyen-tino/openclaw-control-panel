# openclaw-panel

Python (Flask 3 + gunicorn/gevent) + React 18 (Vite + Tailwind + shadcn-style) management panel for self-hosted OpenClaw VPS. Drop-in replacement for the legacy Node management API at `vps-openclaw-management` with full v2.0.3 feature parity + a modern SPA + SSE log streaming.

## Architecture

```
Internet
  │
  ▼
┌─────────────────────────────────────┐
│ Caddy 2 (systemd) — :80 / :443      │ ← reverse proxy + Let's Encrypt
└─────────────┬───────────────────────┘
              │
   ┌──────────┴────────────┐
   ▼                       ▼
openclaw.service       openclaw-mgmt.service
(npm openclaw)         (gunicorn -k gevent wsgi:app)
port 18789             port 9998
                       │
                       ├─ /api/* → Flask blueprints
                       └─ /     → React SPA (static/dist)
```

State files stay byte-compatible with the legacy install (`.env`, `openclaw.json`, per-agent `auth-profiles.json`, `devices/{pending,paired}.json`) so an existing source-installed VPS can drop its files onto the new layout without migration.

## Quick start (VPS install)

```bash
curl -fsSL https://<release-host>/install.sh | sudo bash -s -- \
    --domain panel.example.com \
    --release-base https://<release-host>/releases/openclaw-panel \
    [--mgmt-key <KEY>] [--tag v1.0.0] [--legacy-routing] [--skip-chrome]
```

Required: Ubuntu 22.04 or 24.04. The script installs Node 24, Caddy 2, Python 3.12 (deadsnakes PPA on 22.04), and 3 systemd services. See `docs/install-guide.md` for flag reference + idempotency notes.

## Local development

```bash
make install-dev      # python venv + npm install
make dev-api          # gunicorn on 127.0.0.1:9998 with autoreload
make dev-ui           # vite dev server on :5173, proxies /api → :9998
make test             # pytest (112 tests)
make build-ui         # vite build → static/dist/
make lint format      # ruff + black + mypy
```

Set `OPENCLAW_HOME=/tmp/openclaw-dev` to keep dev state out of `/opt`.

## Project layout

```
openclaw-panel/
├── app/
│   ├── __init__.py            # Flask factory + blueprint wiring
│   ├── config.py              # PATHS, OAuth constants, CIDR whitelist
│   ├── auth.py                # scrypt + Bearer + rate-limit
│   ├── extensions.py          # flask-limiter
│   ├── caddy/
│   │   └── Caddyfile.template
│   ├── providers/
│   │   ├── known_models.py    # 22 built-in providers (ported from server.js)
│   │   ├── template_loader.py
│   │   ├── key_tester.py
│   │   └── templates/         # 23 provider JSON files
│   ├── routes/                # 13 route blueprints
│   ├── services/              # 20+ business-logic modules
│   └── utils/                 # secrets, dotenv-atomic, ip-cidr, subprocess
├── ui/
│   ├── package.json, vite.config.ts, tailwind.config.js
│   └── src/
│       ├── main.tsx, App.tsx, index.css
│       ├── lib/               # api, sse, format, cn
│       ├── components/        # ui primitives + layout shell
│       └── routes/            # 10 SPA pages
├── tests/                     # pytest unit + integration + e2e/Playwright
├── systemd/                   # service units shipped in install tarball
├── scripts/build-release-tarball.sh
├── install.sh
├── wsgi.py
└── Makefile
```

## Backend endpoints (56 routes)

See `docs/api-reference.md` for the full contract. Highlights:

- `GET /api/health` — public liveness probe
- `POST /api/auth/login` — public; returns gateway token
- `GET|POST|PUT|DELETE /api/agents[...]`, `/api/bindings`, `/api/channels`
- `PUT /api/config/provider` — switch model with `openclaw.json` schema preserved
- `POST /api/config/chatgpt-oauth/{start,complete,refresh}` — PKCE OAuth for Codex
- `GET /api/logs/stream`, `GET /api/terminal/stream` — SSE
- `GET /pair?token=…` — public; activates 60s pairing window

All `/api/*` (except `/api/health`, `/api/auth/login`, `/pair`) require `Authorization: Bearer <OPENCLAW_MGMT_API_KEY>`.

## Differences from the Node source

| Area | Source (v2.0.3) | openclaw-panel |
|------|------------------|----------------|
| Runtime | Node 24 raw HTTP | Python 3.12 + Flask 3 + gunicorn/gevent |
| Mgmt API LoC | 3464 (one file) | 20+ modules, each <250 LoC |
| Admin UI | inline HTML strings | React 18 SPA (Vite + Tailwind) |
| `.env` writes | line-by-line replace (corruption risk) | atomic temp + `os.replace` |
| Routing on `/` | gateway 18789 | SPA + management API; gateway moved to `/gateway/*`. Use `--legacy-routing` to keep source layout. |
| Caddyfile source | downloaded from GitHub at runtime | shipped in tarball |
| SPA distribution | n/a | prebuilt tarball; install.sh fetches by tag |
| OAuth client ID | hardcoded | `OPENAI_CODEX_CLIENT_ID` env override (defaults to source value) |

## Migrating from source

1. Capture state: `tar -czf openclaw-state.tgz /opt/openclaw/.env /opt/openclaw/config /opt/openclaw/Caddyfile`.
2. Run new `install.sh` (the legacy Node `/opt/openclaw-mgmt/` is renamed to `-legacy-<ts>/`).
3. State files are byte-compatible — `.env`, `openclaw.json`, `auth-profiles.json`, `devices/*.json` keep working.

See `docs/migration-notes.md` for caveats (Caddy routing change, OAuth refresher timing, rate-limiter reset).

## License

MIT (or your choice — fill in before publishing).
