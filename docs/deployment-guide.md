# OpenClaw Panel — Deployment Guide

## One-liner installer

### Public repo (no auth)
```bash
curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh \
  | sudo bash -s -- --domain example.com
```

### Private repo (requires PAT with `repo:read`)
```bash
GH_TOKEN=ghp_xxx
BOOTSTRAP_ID=421275744   # see `gh release view v0.1.0` for current ID

curl -fsSL -H "Authorization: token $GH_TOKEN" -H "Accept: application/octet-stream" \
  -o /tmp/bootstrap.sh \
  "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/assets/$BOOTSTRAP_ID"

sudo GH_TOKEN="$GH_TOKEN" bash /tmp/bootstrap.sh --domain example.com
```

### LAN / internal IP
```bash
sudo GH_TOKEN="$GH_TOKEN" bash /tmp/bootstrap.sh \
  --domain 192.168.232.6 \
  --no-firewall \
  --skip-chrome
```
Caddy issues self-signed cert (`tls internal`) for IP / non-public domains.

### Optional flags forwarded to install.sh
| Flag | Purpose |
|------|---------|
| `--no-firewall` | Skip ufw setup |
| `--skip-chrome` | Skip Google Chrome (saves ~600MB) |
| `--force` | Suppress legacy-detected warnings |
| `--mgmt-key XXX` | Use specific API key instead of auto-generated |
| `--legacy-routing` | Caddy routes `/ → gateway` (source-layout compat) |

## Publishing a new release (maintainer)

```bash
# Bump version, commit, push.
git tag v0.2.0
git push origin v0.2.0

# Build + create GH release + upload assets in one go.
bash scripts/publish-github-release.sh v0.2.0 "release notes here"
```
The script:
1. Builds SPA via `npm run build`
2. Stages app + systemd + scripts + static into `openclaw-panel.tar.gz`
3. Uploads `install.sh`, `bootstrap.sh`, `openclaw-panel.tar.gz` + `.sha256`
4. Emits the per-repo one-liner snippet

## Verified targets
| OS | Notes |
|----|-------|
| Ubuntu 22.04 | Python 3.12 from deadsnakes PPA |
| Ubuntu 24.04 | Python 3.12 native + python3.12-venv apt |

## Post-install
| Endpoint | Purpose |
|----------|---------|
| `https://<DOMAIN>/` | SPA (login, dashboard) |
| `https://<DOMAIN>/api/health` | Liveness probe |
| `https://<DOMAIN>:18790/#token=<gateway-token>` | OpenClaw Gateway Control UI |

Gateway token in `/opt/openclaw/.env` (`OPENCLAW_GATEWAY_TOKEN=`).
MGMT API key printed by installer and stored in `/opt/openclaw/.env` (`OPENCLAW_MGMT_API_KEY=`).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Origin not allowed` on `:18790` | install.sh auto-patches `gateway.controlUi.allowedOrigins`. If missing, run `openclaw doctor --fix` then add domain manually. |
| Telegram bot pairing prompts | Approve via terminal page: `openclaw pairing approve telegram <CODE>` |
| `/chat` blank page on refresh | Caddyfile must use catch-all `handle { reverse_proxy 127.0.0.1:9998 }`. Updated in v0.1.0. |
| Empty `.openclaw/openclaw.json` crash | Stop openclaw, delete the empty file, run `openclaw doctor --fix`. |
