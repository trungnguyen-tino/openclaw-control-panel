# tino-hsm — Deploy + Auto-Update Guide

Tài liệu deploy `tinovn/tino-hsm` (HMS — Hosting Management System) lên VPS Ubuntu mới + thiết lập cơ chế auto-pull bản mới từ GitHub.

> **Quan hệ với openclaw-panel:** `tino-hsm` là service ĐỘC LẬP (Laravel + Next.js + MariaDB + Redis), có module Proxmox tích hợp sẵn để clone VM + cấu hình IP qua cloud-init. `openclaw-panel` là control panel cho OpenClaw gateway, không port code từ `tino-hsm`. Hai service có thể chạy song song (vd: openclaw-panel quản lý gateway, tino-hsm quản lý fleet VPS Proxmox).

---

## 1. Kiến trúc tóm tắt

```
                         VPS Ubuntu 22.04+
        ┌──────────────────────────────────────────────┐
        │  ┌─────────────────┐                         │
Internet│  │  Nginx :80/443  │── reverse proxy ──┐     │
   │    │  │  + Let's Encrypt│                   │     │
   ▼    │  └────────┬────────┘                   ▼     │
*.tikme │           │                  ┌───────────────┐│
.vn ────┼─▶ frontend (Next.js :3000 via PM2)         │
api.tikme.vn ───────┼─▶ backend (PHP-FPM 8.3 :9000)   ││
        │           ▼                  └────┬──────────┘│
        │  ┌──────────────┐                 │           │
        │  │ MariaDB 10.11│◀────────────────┤           │
        │  │ hms_central +│                 │           │
        │  │ hms_tenant_N │      ┌──────────▼──────────┐│
        │  └──────────────┘      │ Redis (queue+cache) ││
        │                        │ + Horizon worker    ││
        │                        └─────────────────────┘│
        └──────────────────────────────────────────────┘
```

**Yêu cầu VPS:** 2 vCPU · 4GB RAM · 40GB SSD · Ubuntu 22.04+

**Multi-tenant qua subdomain:**
- `tikme.vn` → frontend platform admin
- `{slug}.tikme.vn` → frontend tenant admin
- `api.tikme.vn` → backend platform API
- `{slug}.api.tikme.vn` → backend tenant API
- **DNS yêu cầu:** wildcard `*.tikme.vn` + `*.api.tikme.vn` trỏ về IP VPS

---

## 2. Auto-Deploy — VPS mới (one-liner)

> Yêu cầu: SSH root access tới VPS Ubuntu 22.04+ + GitHub PAT với scope `repo:read`.

```bash
# Trên VPS đích, chạy 1 lệnh:
GH_TOKEN=ghp_xxx \
APP_DOMAIN=tikme.vn \
DB_PASSWORD=ChangeMe!2026 \
REDIS_PASSWORD=ChangeMe!2026 \
curl -fsSL -H "Authorization: token $GH_TOKEN" \
  -H "Accept: application/vnd.github.raw" \
  https://api.github.com/repos/tinovn/tino-hsm/contents/scripts/bootstrap-vps.sh \
  | sudo bash
```

Script (`scripts/bootstrap-vps.sh` cần tạo trong `tino-hsm`) sẽ tự:
1. Apt install: PHP 8.3 + extensions, MariaDB, Redis, Node.js 20, Nginx, Certbot, Supervisor, PM2, Composer
2. Tạo swap 2GB nếu RAM ≤ 4GB
3. Init `hms_central` database + user
4. `git clone` repo về `/opt/hms` (dùng PAT)
5. `composer install`, `npm ci && npm run build`
6. Run migrations: central + tenant scaffold
7. Setup Nginx vhost cho `*.${APP_DOMAIN}` + `api.*` + `*.api.*`
8. Certbot issue wildcard cert (DNS-01 thường cần — guide riêng)
9. Setup Supervisor cho `hms-horizon`, PM2 cho `hms-frontend`
10. Tạo `auto-update.timer` systemd (xem section 4)

> **Bước 1 (tạo `bootstrap-vps.sh` trong tino-hsm repo):** đây là tiền điều kiện. Hiện nay tino-hsm có `deploy.sh` (in-place update) nhưng KHÔNG có fresh-install script. Cần PR thêm script này theo cấu trúc của `DEPLOYMENT.md` (đã có hướng dẫn step-by-step).

---

## 3. Manual deploy (link upstream)

Hiện tại tino-hsm có sẵn:
- `DEPLOYMENT.md` (744 lines) — hướng dẫn full manual install
- `deploy.sh` (49 lines) — update workflow (git pull + composer + migrations + restart)
- `docker-compose.yml` — Docker mode (nhanh hơn cho dev/test)

**Manual fresh install:**
```bash
ssh root@<VPS-IP>
git clone https://github.com/tinovn/tino-hsm.git /opt/hms
cd /opt/hms
cat DEPLOYMENT.md  # follow step-by-step
```

**Docker compose (dev/test):**
```bash
cd /opt/hms
cp docker/.env.example docker/.env
# edit DB_PASSWORD, REDIS_PASSWORD, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_APP_DOMAIN
docker compose up -d
```

---

## 4. Auto-update từ GitHub (3 phương án)

### Phương án A — systemd timer (Recommended)

Kéo `main` branch + chạy `deploy.sh` mỗi 6 giờ. An toàn nhất vì kiểm soát thời điểm.

**Tạo `/etc/systemd/system/hms-auto-update.service`:**
```ini
[Unit]
Description=HMS auto-update from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/hms
ExecStart=/opt/hms/deploy.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Tạo `/etc/systemd/system/hms-auto-update.timer`:**
```ini
[Unit]
Description=Run hms-auto-update every 6 hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
```

**Kích hoạt:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hms-auto-update.timer
sudo systemctl list-timers hms-auto-update.timer
```

**Theo dõi log:**
```bash
journalctl -u hms-auto-update.service -n 50 --no-pager
```

**Ưu:** Cron-like, không cần expose webhook port. Có thể tắt qua `systemctl stop hms-auto-update.timer`.
**Nhược:** Update trễ tối đa 6h sau commit. Tăng/giảm `OnUnitActiveSec` tuỳ nhu cầu.

### Phương án B — GitHub webhook → instant deploy

VPS lắng nghe HTTP webhook từ GitHub khi có push vào `main`.

**1. Tạo webhook listener** (FastAPI hoặc PHP route trong `api_backend`):
```python
# scripts/webhook-listener.py
import hmac, hashlib, subprocess, os
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()
SECRET = os.environ["GITHUB_WEBHOOK_SECRET"].encode()

@app.post("/webhook")
async def webhook(req: Request, x_hub_signature_256: str = Header(...)):
    body = await req.body()
    expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(401, "bad signature")
    subprocess.Popen(["/opt/hms/deploy.sh"])
    return {"ok": True}
```

Chạy qua systemd unit + Nginx reverse proxy `/hooks/deploy` → `127.0.0.1:8001`.

**2. Trong GitHub repo settings → Webhooks → Add:**
- Payload URL: `https://api.tikme.vn/hooks/deploy`
- Content type: `application/json`
- Secret: `<GITHUB_WEBHOOK_SECRET>` (lưu trong `.env`)
- Events: Just the push event

**Ưu:** Deploy gần real-time, < 1 phút sau khi merge.
**Nhược:** Cần public endpoint + manage shared secret + handle deploy failures gracefully.

### Phương án C — GitHub Actions self-hosted runner

VPS đăng ký làm runner, GitHub Actions auto trigger workflow build/deploy.

```yaml
# .github/workflows/deploy.yml (trong tino-hsm repo)
name: Auto-deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - name: Deploy
        run: |
          cd /opt/hms
          ./deploy.sh
```

**Ưu:** Native GitHub integration, có UI run history, retries, secrets management.
**Nhược:** Cần install Actions runner trên VPS + maintain.

---

## 5. Cấu hình Proxmox + NPM credentials

tino-hsm module Proxmox (`api_backend/app/Modules/Providers/Proxmox/`) cần credentials trong DB hoặc `.env`:

```env
# /opt/hms/api_backend/.env (additional vars)
PROXMOX_HOST=192.168.1.10
PROXMOX_PORT=8006
PROXMOX_TOKEN_ID=root@pam!tinohsm
PROXMOX_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PROXMOX_VERIFY_TLS=false
PROXMOX_DEFAULT_NODE=pve01
PROXMOX_DEFAULT_STORAGE=local-lvm
PROXMOX_DEFAULT_BRIDGE=vmbr0
```

**Tạo API token trên Proxmox:**
1. Web UI → Datacenter → Permissions → API Tokens → Add
2. User: `root@pam`, Token ID: `tinohsm`, ❌ uncheck "Privilege Separation"
3. Copy token secret → paste vào `.env`

### NPM (Nginx Proxy Manager) — GAP cần build

tino-hsm **chưa có** module NPM. Theo recon, NPM REST API không có docs public + có thể break ngang version. Nếu cần auto-add proxy host khi clone VM:

**Option 1 (đơn giản):** Manual — sau khi `tino-hsm` provision VM xong, vào NPM UI thêm proxy host trỏ về `<NEW_VM_IP>`.

**Option 2 (đề xuất build):** Tạo Laravel service `NginxProxyManagerService` trong `api_backend/app/Services/`. Endpoint cần dùng:
```
POST {NPM_HOST}:81/api/tokens          # auth, trả về JWT
POST {NPM_HOST}:81/api/nginx/proxy-hosts  # tạo proxy host
DELETE /api/nginx/proxy-hosts/{id}     # xoá khi terminate VM
```
Body example:
```json
{
  "domain_names": ["customer-abc.tikme.vn"],
  "forward_scheme": "http",
  "forward_host": "192.168.1.50",
  "forward_port": 80,
  "websockets_support": true,
  "ssl_forced": true,
  "letsencrypt_email": "admin@tikme.vn"
}
```

**Issue cần PR vào tino-hsm:** `Add NginxProxyManagerService for auto proxy host CRUD on VM provision/terminate`.

---

## 6. Lifecycle hook khi clone VM xong

Trong `ProxmoxModule::provision()` đã có IPAM (static IP via cloud-init). Đề xuất extension:

```php
// Pseudo-code — sau khi VM lên + ping được
public function provision(array $params): array {
    // ... existing clone logic ...
    $serverIp = $params['ipam_ip'];

    // NEW: register với NPM
    if (config('hms.npm.enabled')) {
        app(NginxProxyManagerService::class)->createProxyHost([
            'domain_names' => [$params['hostname']],
            'forward_host' => $serverIp,
            'forward_port' => 80,
        ]);
    }
    return [...];
}
```

---

## 7. Monitoring + troubleshooting

| Symptom | Check |
|---|---|
| Auto-update không chạy | `systemctl status hms-auto-update.timer` + `journalctl -u hms-auto-update` |
| `git pull` fail (auth) | Cần PAT trong remote URL: `git remote set-url origin https://${GH_TOKEN}@github.com/tinovn/tino-hsm.git` |
| Composer install hang | RAM thấp → tạo swap 2GB |
| Horizon worker chết sau update | `sudo supervisorctl restart hms-horizon` |
| Next.js build OOM | Set `NODE_OPTIONS="--max-old-space-size=4096"` |
| Proxmox connection refused | Verify token + URL via `curl -k https://${PROXMOX_HOST}:8006/api2/json/version -H "Authorization: PVEAPIToken=${PROXMOX_TOKEN_ID}=${PROXMOX_TOKEN_SECRET}"` |
| NPM proxy host duplicate | NPM API trả 409. Cần fetch list, check trùng `domain_names` trước khi POST |

---

## 8. Bảo mật

- `.env` files: `chmod 600 /opt/hms/api_backend/.env`
- DB user `hms_user` chỉ có quyền trên `hms_central` + `hms_tenant_%`
- Redis: bắt buộc `requirepass`
- GitHub PAT: scope **chỉ `repo:read`** + rotate 90 ngày
- Webhook secret: 32-byte random, lưu chỉ trong `.env`
- Nginx: tắt `server_tokens`, bật HSTS
- Auto-update timer: nếu deploy fail, có thể `RestartSec=` để retry; nhưng **không retry vô hạn** (`StartLimitBurst=3` trong `[Unit]`)

---

## 9. Roadmap đề xuất (PR vào tino-hsm)

| # | Feature | Mức ưu tiên | Estimate |
|---|---|:-:|---|
| 1 | `scripts/bootstrap-vps.sh` (fresh install one-liner) | High | 2h |
| 2 | `NginxProxyManagerService` + hook vào provision/terminate | High | 4h |
| 3 | systemd `hms-auto-update.timer` (ship trong installer) | Medium | 1h |
| 4 | Webhook listener (FastAPI Sidecar hoặc Laravel route) | Medium | 3h |
| 5 | Proxmox `terminate()` auto cleanup NPM | Medium | 1h |
| 6 | Health check endpoint cho post-deploy verify | Low | 1h |

---

## Open questions

- **Proxmox cluster vs single node?** Hiện ProxmoxApi support `listNodes()` + selectionStrategy. Cần test multi-node clone với storage migration.
- **DNS wildcard cert?** Let's Encrypt DNS-01 cần API token với DNS provider (Cloudflare/Vultr/...). Quy trình per-provider khác nhau.
- **NPM API version compatibility?** Test với NPM 2.10+ (current). Ghi nhớ break điểm trong code comments.
- **Schedule auto-update với business hours?** systemd timer hỗ trợ `OnCalendar=Mon..Fri 03:00:00` cho production-safe deploy.

---

## Tham khảo

- tino-hsm repo: https://github.com/tinovn/tino-hsm (private)
- Architecture diagram: `Architecture_Diagram.md` trong repo
- Manual deployment full: `DEPLOYMENT.md` trong repo
- Proxmox API: https://pve.proxmox.com/wiki/Proxmox_VE_API
- Nginx Proxy Manager: https://nginxproxymanager.com/
