# System architecture

## Process topology

```
┌────────────┐  TLS  ┌──────────────────────────┐
│  Internet  │──────▶│  Caddy 2 (:80/:443)       │
└────────────┘       │  Let's Encrypt / internal │
                     └─────────┬─────────────────┘
                               │ reverse_proxy
              ┌────────────────┴─────────────────┐
              ▼                                  ▼
     ┌──────────────────┐               ┌────────────────────┐
     │ openclaw         │ ◀── gateway──▶│ openclaw-mgmt      │
     │ (npm: openclaw)  │   /gateway/*  │ (gunicorn gevent)   │
     │ :18789           │               │ :9998               │
     └────────┬─────────┘               │  ┌───────────────┐ │
              │                          │  │ Flask routes  │ │
              │                          │  │  /api/*       │ │
              ▼                          │  └───────────────┘ │
        File-based state                 │  ┌───────────────┐ │
        /opt/openclaw/                   │  │ React SPA     │ │
                                          │  │  static/dist  │ │
                                          │  └───────────────┘ │
                                          └────────────────────┘
```

All three units run as `root` (parity with the source — needed for `systemctl` and file ownership). Future hardening: drop privileges + sudoers rules.

## Process model

- **Single gunicorn worker, gevent class**. Required for SSE streams (sync workers block). Single worker keeps in-memory rate-limit counters + OAuth session store coherent (acceptable trade-off documented in source).
- `--timeout 300` accommodates long-running SSE.

## State storage

| File | Purpose | Writers |
|------|---------|---------|
| `/opt/openclaw/.env` | tokens, domain, all API keys | atomic via `tempfile + os.replace`, lock per process |
| `/opt/openclaw/config/openclaw.json` | active provider, model, bindings, channels, agents list | atomic |
| `/opt/openclaw/config/agents/<id>/agent/auth-profiles.json` | per-agent API keys + OAuth tokens | atomic |
| `/opt/openclaw/config/devices/{pending,paired}.json` | device pairing | atomic |
| `/opt/openclaw/Caddyfile` | reverse-proxy config | written on domain change |

## Key code paths

### Provider switch (`PUT /api/config/provider`)

```
config_routes.put_provider
  └─ provider_service.switch_provider(provider, model)
       ├─ template_loader.load_template(provider)
       ├─ openclaw_config_service.read()
       ├─ openclaw_config_service.merge_template(current, template, provider, model)
       │     ├─ preserve agents.list, bindings, channels
       │     └─ set agents.defaults.model.primary = "<provider>/<model>"
       ├─ openclaw_config_service.write_atomic(merged)
       └─ systemd_service.restart("openclaw")
```

### OAuth Codex flow

```
SPA → POST /api/config/chatgpt-oauth/start
        └─ pkce_service.gen_verifier + s256_challenge
        └─ SessionStore.add(sid → verifier, agent_id, 10-min expiry)
        └─ return {oauthUrl, sessionId}

SPA opens oauthUrl in browser, user signs into ChatGPT
User pastes redirect URL into SPA prompt
SPA → POST /api/config/chatgpt-oauth/complete {sessionId, redirectUrl}
        └─ extract `code` from redirect
        └─ POST auth.openai.com/oauth/token {grant_type, code_verifier, ...}
        └─ decode id_token (unsigned) → email
        └─ auth_profiles_service.set_oauth_profile(agent_id, "openai-codex:<email>", payload)
        └─ if switchProvider: provider_service.switch_provider("openai-codex", model)

Background daemon thread (oauth_refresher_thread):
  every 60s:
    list_oauth_profiles_for_all_agents()
    for each profile where expires - now < 10 min and not dead:
      POST auth.openai.com/oauth/token {grant_type:refresh_token, ...}
      → on success: update access + expires
      → on invalid_grant: mark dead:true
```

### Domain change (`PUT /api/domain`)

```
domain_routes.put_domain
  └─ domain_change_service.change_domain(new_domain)
       ├─ snapshot .env + Caddyfile bytes
       ├─ dns_check_service.resolve_a(domain) via Cloudflare DoH
       ├─ tls = "" if DNS resolves to server_public_ip else "tls internal"
       ├─ dotenv_set("DOMAIN", new); dotenv_set("CADDY_TLS", tls)
       ├─ caddy_service.render_and_write()
       ├─ caddy_service.restart()
       └─ if not is_active() within 1s: ROLLBACK env + Caddyfile + restart
```

### SSE log stream

```
SPA opens EventSource("/api/logs/stream?service=openclaw&token=KEY")
  └─ info_routes.logs_stream (Bearer or ?token=)
       └─ stream_journalctl(service)
            └─ subprocess.Popen(["journalctl","-u",svc,"-f", ...], stdout=PIPE)
            └─ for each line: yield "data: {\"line\":\"...\"}\n\n"
            └─ on timeout/error: yield "event: end\ndata:{...}\n\n"
```

## Security boundary

| Boundary | Protection |
|----------|------------|
| Internet → Caddy | TLS (Let's Encrypt or self-signed) |
| Caddy → mgmt API | Loopback only (127.0.0.1:9998); Bearer required for `/api/*` (except `/api/health`, `/api/auth/login`, `/pair`) |
| Mgmt API → subprocess | `subprocess_safe.run_cmd` — args=list only, scrubbed env, no shell |
| Mgmt API → `.env` | atomic write + chmod 0600 |
| Bearer brute-force | 10 fails / 15 min / IP → 429; CIDR whitelist bypasses rate-limit but **not** auth |
| CLI proxy | regex blocks shell metacharacters + exact-prefix whitelist + `subprocess shell=False` |

## Observability

- All output → journald via `journalctl -u openclaw-mgmt`.
- Upgrade/self-update use their own file logs under `/var/log/openclaw-mgmt/`.
- `/api/health` is the canonical liveness probe.
- No external telemetry / metrics emission (out of MVP).
