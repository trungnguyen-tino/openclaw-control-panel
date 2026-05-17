# Migration: Node v2.0.3 → openclaw-panel v1.0.0

State files are byte-compatible — you don't need to rewrite anything. Behavior diverges in a few places that matter for ops.

## Filesystem layout

Unchanged: `/opt/openclaw/.env`, `/opt/openclaw/config/openclaw.json`, `/opt/openclaw/config/agents/<id>/agent/auth-profiles.json`, `/opt/openclaw/config/devices/{pending,paired}.json`.

Moved: `/opt/openclaw-mgmt/server.js` (Node) → `/opt/openclaw-mgmt/wsgi.py` + `app/` (Python). The legacy tree is backed up to `/opt/openclaw-mgmt-legacy-<ts>/` automatically.

## Behavior changes

| Area | Source | openclaw-panel |
|------|--------|----------------|
| `.env` writes | line-by-line in-place (can corrupt on kill -9) | tempfile + `os.replace` (POSIX-atomic) |
| Caddy routing | `/` → openclaw gateway (18789); `/login`, `/api/auth/*` → mgmt | `/` → SPA + mgmt API; `/gateway/*` → gateway. Pass `--legacy-routing` to keep source layout. |
| Caddyfile source | downloaded from GitHub at runtime (on domain change) | shipped in tarball at `app/caddy/Caddyfile.template` |
| OAuth client ID | hardcoded `app_EMoamEEZ73f0CkXaXp7hrann` | same default + `OPENAI_CODEX_CLIENT_ID` env override |
| Rate limit storage | in-memory (resets on restart) | unchanged (single gunicorn worker = same behavior) |
| SPA distribution | n/a — inline HTML | prebuilt tarball; never builds Node on VPS |
| `OPENCLAW_MGMT_API_KEY` rotation | manual edit `.env` + restart | same; locked from `PUT /api/env/<key>` for safety |

## API compatibility

Every public endpoint from the source v2.0.3 API is present. Verified by `tests/test_endpoint_contract.py` (56 routes total, all asserted).

New endpoints:
- `GET /api/health` (used by install.sh post-install check).
- `GET /api/logs/stream` (SSE live tail).

## Caddy routing breakage

If your existing clients hit `/some/path` expecting the openclaw gateway response, they now get the SPA. Two options:

1. Pass `--legacy-routing` to the installer — restores the source layout (gateway at `/`).
2. Update clients to hit `/gateway/<path>` instead.

## OAuth refresher

- Background thread starts on first request (skipped in `TESTING=True`).
- Polls every 60s; refreshes tokens with <10 min remaining.
- `invalid_grant` from OpenAI marks profile `dead:true` — surfaced in `GET /api/agents/<id>`. User must re-authenticate.

## Tokens & secrets

- Existing `OPENCLAW_LOGIN_PASS` (scrypt N=16384, r=8, p=1, dklen=64) verifies unchanged — same algorithm + params.
- Per-device tokens regenerate on each `/api/devices/approve/<id>` call (no rotation strategy yet — same as source).
- ChatGPT OAuth sessions are in-memory and expire after 10 min (source had same limitation).

## Rolling back

If the new install breaks something critical:

```bash
systemctl stop openclaw-mgmt
LEGACY=$(ls -td /opt/openclaw-mgmt-legacy-* | head -1)
mv /opt/openclaw-mgmt /opt/openclaw-mgmt-py-broken
mv "$LEGACY" /opt/openclaw-mgmt
# Restore the legacy systemd unit
cat > /etc/systemd/system/openclaw-mgmt.service <<'EOF'
[Unit]
Description=OpenClaw Management API (legacy Node)
After=network-online.target openclaw.service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/openclaw-mgmt
ExecStart=/usr/bin/node /opt/openclaw-mgmt/server.js
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl restart openclaw-mgmt
```

Configuration (`.env`, agents, devices) survives the swap since the directories aren't touched.

## Verification checklist

After installing:

- [ ] `curl http://127.0.0.1:9998/api/health` returns `{"ok":true,...}`.
- [ ] `curl -H "Authorization: Bearer $KEY" .../api/info` returns the same fields as the source.
- [ ] `https://<DOMAIN>/` shows the React SPA login page.
- [ ] Existing agent's API keys still work in `openclaw` (no auth-profiles changes needed).
- [ ] `systemctl status openclaw caddy openclaw-mgmt` — all three active.
