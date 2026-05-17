# Install guide

## Supported OS

- Ubuntu 22.04 (Python 3.12 installed from deadsnakes PPA).
- Ubuntu 24.04 (native Python 3.12 package).

Other distros not tested; PRs welcome.

## Prerequisites

- Root access (`sudo`).
- 1 vCPU / 1 GB RAM minimum. 2 vCPU / 2 GB recommended.
- DNS A record pointing your domain at the VPS IP (for Let's Encrypt). Self-signed cert is auto-used if DNS doesn't resolve to this server's public IP.
- Outbound HTTPS to: github.com / your release host (tarball), api.openai.com (Codex OAuth), Cloudflare 1.1.1.1 (DNS-over-HTTPS).

## 1-liner install

```bash
curl -fsSL https://<release-host>/install.sh | sudo bash -s -- \
  --domain panel.example.com \
  --release-base https://<release-host>/releases/openclaw-panel
```

Replace `<release-host>` with where the release tarball lives (GitLab Releases, GitHub Releases, or self-hosted). The installer expects two URLs to be reachable:

```
${RELEASE_BASE}/openclaw-panel-${TAG}.tar.gz
${RELEASE_BASE}/openclaw-panel-${TAG}.tar.gz.sha256   (optional — checksum verification)
```

`${TAG}` defaults to `latest`; override with `--tag v1.0.0`.

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--domain X` | required | FQDN or `http://<IP>`. Determines Let's Encrypt vs self-signed. |
| `--mgmt-key X` | random 32-byte hex | Bearer key for `/api/*`. Stored in `.env`. |
| `--tag vN` | `latest` | Release tag to fetch from `--release-base`. |
| `--release-base URL` | env `OPENCLAW_PANEL_RELEASE_BASE` | Where tarball + sha256 live. |
| `--legacy-routing` | off | Caddy routes `/` → openclaw gateway (source-compat). Default: `/` → SPA. |
| `--no-firewall` | off | Skip UFW. |
| `--skip-chrome` | off | Skip Google Chrome (saves ~200 MB). |
| `--force` | off | Suppress legacy-detection warnings. |

## Build a release locally

```bash
make build-ui                          # vite build → static/dist/
bash scripts/build-release-tarball.sh v1.0.0
# Output: dist/openclaw-panel-v1.0.0.tar.gz + .sha256
```

Upload both to your release host. The companion CI workflow at `.github/workflows/release.yml` does this automatically on a `v*` git tag push.

## What the installer does

1. Validate root + Ubuntu version.
2. Stop unattended-upgrades + clear apt locks.
3. `apt-get update` + install base packages (curl, jq, ufw, fail2ban, ...).
4. Install Node 24 (if absent).
5. `npm install -g openclaw@latest` (if absent).
6. Install Google Chrome (skippable).
7. Install Caddy 2 from official repo.
8. Configure UFW (open 80/443/9998).
9. Install Python 3.12 (deadsnakes on 22.04).
10. Backup any legacy `/opt/openclaw-mgmt/server.js` to `/opt/openclaw-mgmt-legacy-<ts>/`.
11. Fetch + verify panel tarball, extract to `/opt/openclaw-mgmt/`.
12. Create venv at `/opt/openclaw-mgmt/.venv/`, `pip install -r requirements.txt`.
13. Generate fresh `.env` (or preserve if exists) with random tokens.
14. Seed `/etc/openclaw/config/*.json` provider templates (if empty).
15. Render Caddyfile.
16. Write 3 systemd units + enable + start.
17. Health-check `GET /api/health` for up to 30s.
18. Print dashboard URL + MGMT API key.

## Idempotency

Re-running with the same flags is safe:

- `.env`, `openclaw.json`, `auth-profiles.json` preserved.
- `/etc/openclaw/config/*.json` preserved (templates copied only if dir is empty).
- venv recreated cleanly each run; service restarted.

## Verifying the install

```bash
systemctl is-active openclaw caddy openclaw-mgmt
curl -fsS http://127.0.0.1:9998/api/health | jq

# Tail logs
journalctl -u openclaw-mgmt -f
journalctl -u openclaw -f
journalctl -u caddy -f
```

## Uninstall

```bash
systemctl disable --now openclaw openclaw-mgmt caddy
rm -rf /opt/openclaw /opt/openclaw-mgmt /opt/openclaw-mgmt-legacy-*
rm /etc/systemd/system/openclaw{,-mgmt}.service
rm /etc/systemd/system/caddy.service.d/override.conf
systemctl daemon-reload
apt-get remove -y caddy nodejs google-chrome-stable
```

## Troubleshooting

**Tarball 404** — Wrong `--release-base` or `--tag`. Pass full URL or set env var. `curl -I "${RELEASE_BASE}/openclaw-panel-${TAG}.tar.gz"` should return 200.

**deadsnakes PPA fails on 22.04** — Manually install Python 3.12 (`apt install python3.12-full` once added). Re-run installer; it detects existing Python.

**Port 9998 already in use** — Find the offender: `ss -tlnp | grep 9998`. Likely legacy Node mgmt. `systemctl stop openclaw-mgmt` first, then re-run.

**Caddy fails to start** — Check Caddyfile syntax: `caddy validate --config /opt/openclaw/Caddyfile`.

**Cannot reach `/api/health`** — Likely binding issue. `gunicorn` should bind `0.0.0.0:9998`. Check `journalctl -u openclaw-mgmt -n 50`.
