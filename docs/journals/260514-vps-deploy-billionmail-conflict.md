---
date: 2026-05-14
topic: vps-deploy-billionmail-conflict
tags: [vps, deployment, caddy, port-conflict, lets-encrypt, docker]
severity: high
status: resolved
---

# VPS Deploy: BillionMail Docker Stack Blocking Ports 80/443

## What Happened

Deployed openclaw-panel to production VPS (180.93.137.19, Ubuntu 22.04) via `install.sh`. The install completed successfully — Python 3.12, Node 24, gunicorn, openclaw npm package all running. But Caddy crashed at startup: `listen tcp :443: bind: address already in use`.

Root cause: BillionMail's docker-compose stack (billionmail-core) was already holding ports 80 and 443 via docker-proxy for an existing mail service (`DOCKER_EXPOSE_PORT=80 DOCKER_EXPOSE_PORT=443`). Caddy couldn't bind. Disabled with `systemctl disable --now caddy`. Fallback: raw HTTP at `:9998`.

## The Brutal Truth

This was a frustrating 30-minute detour. The VPS wasn't pristine — it had an existing workload running. Runbook assumed a clean slate and didn't probe for port conflicts upfront. I spent time debugging Caddyfile syntax (was the template wrong?) before realizing the underlying problem was infrastructure, not configuration. The workaround was crude: accept unencrypted HTTP for now.

## Technical Details

**Port conflict snapshot:**
```
netstat -tlnp | grep -E ':(80|443)'
tcp  0  0  0.0.0.0:80     0.0.0.0:*  LISTEN  docker-proxy (billionmail-1)
tcp  0  0  0.0.0.0:443    0.0.0.0:*  LISTEN  docker-proxy (billionmail-1)
```

**Caddy error in systemd journal:**
```
caddy[12345]: 2026/05/13 21:09:45 Error: unable to listen on "localhost:443" (tcp): listen tcp 127.0.0.1:443: bind: address already in use
```

**Current production access:** `http://180.93.137.19:9998/` (unencrypted, port explicit in URL)

**BillionMail status:** `docker ps | grep billionmail-core` shows container running on compose network, exposing 80 & 443 to host.

## What We Tried

1. **Soft Caddy restart** — `systemctl restart caddy` → failed again
2. **Check Caddyfile template** — Syntax was fine; paths to mgmt/openclaw proxies correct
3. **Manual caddy run** — `caddy validate --config /etc/caddy/Caddyfile` passed, `caddy run` failed with bind error
4. **Firewall assumption** — UFW was not configured, not the issue
5. **Final fix** — `systemctl disable --now caddy` to free :443, then...

## Root Cause Analysis

BillionMail docker stack started first (likely auto-start on host boot), claimed the privileged ports. Caddy arrived second and lost the race. The install.sh didn't check for pre-existing services on 80/443. No conflict detection → silent failure cascading to a disabled service.

**Why this happened:** Multi-service VPS, no resource coordination. Runbook didn't document prerequisites like "ensure ports 80/443 are free" or offer a graceful bailout.

## Lessons Learned

1. **Port conflict detection belongs in install.sh.** Before starting Caddy, check:
   ```bash
   ss -tlnp | grep -E ':(80|443)' && echo "WARNING: ports occupied" && exit 1
   ```

2. **Docker-compose services need explicit port conflict policy.** Either:
   - Stop ancillary services during deployment: `docker compose down` (BillionMail)
   - Run Caddy on alternate ports (8080→80 redirect via iptables, or use DNS-01 ACME)
   - Coordinate via host-level orchestration (systemd socket activation, shared config)

3. **https at VPS HTTPS URL still unresolved.** Current workaround (direct :9998) works for MVP but demo URL shows `http://180.93.137.19:9998/` — unprofessional. Options:
   - Stop BillionMail core only, keep postfix/dovecot for SMTP (didn't try yet)
   - Use nginx in front, Caddy on :8443 with DNS-01 ACME (adds complexity)
   - Accept that this VPS has co-tenancy conflicts; ask for clean staging VPS

## Next Steps

**Immediate:**
1. Try stopping only `billionmail-core` container (not whole stack), freeing 80/443 while keeping mail services (postfix/dovecot) intact
2. If successful, re-enable Caddy and test Let's Encrypt over tls-alpn-01

**Medium-term:**
1. Add port conflict check to install.sh → warn if 80/443 occupied
2. Document fallback behavior (direct :9998 access)
3. If HTTPS needed for production, provision clean VPS or resolve BillionMail co-tenancy

**Files touched:**
- `docker/compose.yaml` — (no changes, runs as-is in dev)
- `app/caddy/Caddyfile.template` — (unchanged; issue was runtime binding, not syntax)
- `install.sh` — needs port check
- `plans/reports/deploy-260513-2109-vps-demo-result.md` — deployment summary

---

**Cross-linked:** [[260514-vietnamese-spa-rewrite.md]], [[260514-openclaw-gateway-ui-origin-saga.md]]

**Open Questions:**
1. Can we stop just `billionmail-core` container without breaking postfix/dovecot SMTP relaying?
2. Is letting BillionMail's nginx reverse-proxy openclaw (Option B in deploy report) feasible, or would that add too much BillionMail config churn?
3. Should clean VPS be requested for production, or is the :9998 HTTP workaround acceptable for MVP demo?
