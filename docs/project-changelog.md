# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org).

## [1.0.0] — 2026-05-13

### Added

- Initial Python (Flask 3 + gunicorn/gevent) + React 18 (Vite + Tailwind) port of `vps-openclaw-management` v2.0.3.
- 56 backend routes covering full v2.0.3 feature parity:
  - Info / status / control (13 routes).
  - 22 built-in provider catalog + custom provider CRUD (9 routes).
  - Multi-agent CRUD with per-agent `auth-profiles.json` (8 routes).
  - Routing bindings (4 routes).
  - Messaging channels: Telegram, Discord, Slack, Zalo (3 routes).
  - ChatGPT Codex OAuth PKCE with background auto-refresh (3 routes).
  - Device pairing with 60s polling window (3 routes).
  - CLI proxy + SSE terminal stream with metachar whitelist.
  - Domain change with DNS-via-DoH + full Caddyfile rollback.
  - Env-var management with locked keys.
  - Public `/api/health` for install.sh post-install check.
- React SPA with 10 pages: Login, Dashboard, Providers, Agents, Bindings, Channels, Devices, Logs (SSE), Terminal (SSE), Settings.
- 112 pytest tests including endpoint-contract validation.
- Playwright e2e skeleton with login spec.
- `install.sh` for Ubuntu 22.04 (deadsnakes PPA) + 24.04 (native Python 3.12), with idempotent re-runs + legacy Node mgmt-api backup.
- 3 systemd units: `openclaw.service`, `openclaw-mgmt.service`, Caddy override.
- `scripts/build-release-tarball.sh` + GitHub Actions release workflow.

### Changed (vs. source)

- `.env` writes use atomic `tempfile + os.replace` instead of line-by-line in-place (corruption-safe under SIGKILL).
- Default Caddy routing: `/` → SPA + mgmt-API; `/gateway/*` → OpenClaw gateway. Pass `--legacy-routing` to keep source layout.
- Caddyfile shipped in the release tarball; no longer downloaded from GitHub at runtime.
- ChatGPT Codex OAuth client ID supports `OPENAI_CODEX_CLIENT_ID` env override (default unchanged).
- Single 3464-LoC server.js → 20+ modules, each <250 LoC (per CLAUDE.md modularization rule).

### Security

- Subprocess hardening: every shell-touching call uses `subprocess_safe.run_cmd` (list args, scrubbed env, `shell=False`).
- CLI whitelist rejects all shell metacharacters before tokenization.
- `.env` chmod 0600 enforced on every write.
- Bearer auth + timing-safe compare + per-IP rate limit (10/15min).
- CIDR whitelist bypasses rate-limit only — not the auth check itself.
- OAuth `id_token` decoded without signature verification (TLS-trust only) — documented in `oauth_codex_service`.

### Known gaps (deferred from MVP)

- Multi-VPS management.
- Postgres/SQLite state backend (still file-JSON, single-writer assumption).
- WebSocket bidirectional terminal (SSE one-way only).
- Custom OAuth client config UI.
- Docker preflight test (manual via VM until needed).
- Lighthouse a11y audit ≥90.
