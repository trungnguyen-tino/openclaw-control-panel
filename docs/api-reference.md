# API Reference

Base URL: `http://127.0.0.1:9998` (behind Caddy at `https://<DOMAIN>`).

Auth: every protected route requires `Authorization: Bearer <OPENCLAW_MGMT_API_KEY>`. `/api/health`, `/api/auth/login`, `/pair` are public.

Errors: `{ok: false, error: "message"}`. Rate-limit (10 fails / 15 min / IP) replies `429 Too Many Requests` with `Retry-After`.

## Public

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | `{ok, version, uptimeSeconds}` |
| POST | `/api/auth/login` | Body `{username, password}`. Returns `{ok, gatewayToken}`. |
| GET | `/pair?token=<GW>` | Validates gateway token → activates 60s auto-approve poller → 302 redirect to `https://<DOMAIN>/`. |

## Authentication management

| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/api/auth/create-user` | `{username, password}` | scrypt-hashes pwd into `OPENCLAW_LOGIN_PASS`. |
| GET | `/api/auth/user` | — | `{configured, username}` |
| PUT | `/api/auth/change-password` | `{password}` | |
| DELETE | `/api/auth/user` | — | Removes both env vars. |

## Info / status

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/info` | Domain, IP, masked tokens, DNS status, SSL mode. |
| GET | `/api/status` | `openclaw + caddy` status + `startedAt`. |
| GET | `/api/version` | OpenClaw + `.env` version. |
| GET | `/api/system` | hostname, OS, uptime, loadavg, memory, disk, node/openclaw versions. |
| GET | `/api/logs?service=X&lines=N` | Tail journalctl. Whitelist: `openclaw`, `caddy`, `openclaw-mgmt`. 1 ≤ N ≤ 1000. |
| GET | `/api/logs/stream?service=X` | SSE live tail. Bearer **or** `?token=` (EventSource limitation). |
| GET | `/api/domain` | DOMAIN + IP + SSL mode + selfSignedSSL flag. |

## Control

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/restart` | `systemctl restart openclaw` |
| POST | `/api/stop`, `/api/start` | |
| POST | `/api/rebuild` | Restart openclaw + caddy |
| POST | `/api/upgrade` | `npm update -g openclaw` (background thread, 202 + log to `/var/log/openclaw-mgmt/upgrade.log`). |
| POST | `/api/reset` | Body `{confirm: "RESET"}` — wipes `config/`, restores `anthropic.json` template, restart. |
| POST | `/api/self-update` | Body `{tag: "vN"}` — downloads tarball, swaps, restarts mgmt. |

## Providers & config

| Method | Path | Body |
|--------|------|------|
| GET | `/api/providers` | List 22 built-ins + custom. |
| GET | `/api/config` | Active provider, model, masked API keys, agents list, bindings, channels. |
| PUT | `/api/config/provider` | `{provider, model}` |
| PUT | `/api/config/api-key` | `{provider, apiKey, agentId?}` |
| DELETE | `/api/config/api-key` | `{provider, agentId?}` |
| POST | `/api/config/test-key` | `{provider, apiKey}` |
| POST | `/api/config/custom-provider` | `{id, baseUrl, model, modelName, api?, apiKey?}` |
| GET | `/api/config/custom-providers` | |
| PUT | `/api/config/custom-provider/<id>` | partial update |
| DELETE | `/api/config/custom-provider/<id>` | |

## Multi-agent

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/agents` | List with `apiKeyCount`. |
| POST | `/api/agents` | `{id, name?, model?, default?}` — id regex `[a-z0-9][a-z0-9-]{0,63}`. |
| GET | `/api/agents/<id>` | Includes masked profile keys. |
| PUT | `/api/agents/<id>` | partial update |
| DELETE | `/api/agents/<id>` | `{deleteData?}` — refuses if last or default. |
| PUT | `/api/agents/<id>/default` | Enforces single-default invariant. |
| GET | `/api/agents/<id>/api-key` | Lists API + OAuth profiles. |
| PUT | `/api/agents/<id>/api-key` | `{provider, apiKey}` |

## Routing bindings

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/bindings` | Indexed array. |
| POST | `/api/bindings` | `{agentId, match: {channel, ...}}` |
| PUT | `/api/bindings/<index>` | partial |
| DELETE | `/api/bindings/<index>` | Shifts indices. |

## Channels

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/channels` | Telegram/Discord/Slack/Zalo status + masked tokens. |
| PUT | `/api/channels/<channel>` | `{token, appToken?, dmPolicy?}` — restarts openclaw. |
| DELETE | `/api/channels/<channel>` | Disables + clears env. |

## OAuth (ChatGPT Codex, PKCE)

| Method | Path | Body |
|--------|------|------|
| POST | `/api/config/chatgpt-oauth/start` | `{agentId?}` → `{sessionId, oauthUrl, models, sessionExpiresIn}` |
| POST | `/api/config/chatgpt-oauth/complete` | `{sessionId, redirectUrl, model?, switchProvider?}` |
| POST | `/api/config/chatgpt-oauth/refresh` | `{agentId?, profileKey?}` |

Background thread refreshes any profile <10 min from expiry every 60s. Invalid_grant marks `dead:true`.

## Devices

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/devices` | `{pending: [...], paired: [...]}` (tokens masked). |
| POST | `/api/devices/approve/<id>` | Move pending → paired, mint per-role tokens. |

## CLI + terminal

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/cli` | `{command}` — whitelist + metachar block. Returns `{stdout, stderr, exitCode}`. |
| GET | `/api/terminal/stream?command=…` | SSE. Bearer or `?token=`. |

CLI whitelist: `openclaw`, `claw`, `systemctl`, `journalctl`, `npm update -g openclaw`, `df`, `free`, `uptime`, `ps`, `uname`, `hostname`, `date`. Any of `;&|<>()`'$\` etc. → 400.

## Domain + env

| Method | Path | Notes |
|--------|------|-------|
| PUT | `/api/domain` | `{domain, forceDnsSkip?}` — DNS via Cloudflare DoH; rolls back on Caddy fail. |
| GET | `/api/env` | All env vars (sensitive keys masked: TOKEN/KEY/SECRET/PASSWORD). |
| PUT | `/api/env/<key>` | `{value}`. Locks: `OPENCLAW_MGMT_API_KEY`. Setting `OPENCLAW_GATEWAY_TOKEN` syncs `openclaw.json.gateway.auth.token`. |
| DELETE | `/api/env/<key>` | Locks: `OPENCLAW_{GATEWAY_TOKEN,MGMT_API_KEY,VERSION,GATEWAY_PORT}`. |
