# OpenClaw Control Panel

Panel quản lý OpenClaw Gateway tự host trên VPS. Stack: Flask 3 + gunicorn/gevent (Python 3.12) + React 18 SPA (Vite + Tailwind + shadcn). Tích hợp Caddy reverse proxy + Let's Encrypt, self-healing healthcheck, OAuth ChatGPT/Codex, multi-agent, terminal SSE.

## Cài đặt trên VPS mới (1 lệnh)

VPS Ubuntu 22.04 / 24.04, chạy với quyền `root`. Lệnh dưới tải bản latest từ GitHub Releases rồi tự cài Node 22, Caddy, Python 3.12, OpenClaw npm, 4 systemd unit.

**Theme mặc định (Tino, màu xanh lá `#14a74b`) — có domain:**
```bash
curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh \
  | sudo bash -s -- --domain panel.example.com
```

**Theme ICTSAIGON (logo xanh dương) — có domain:**
```bash
curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh \
  | sudo bash -s -- --domain panel.example.com --theme ictsaigon
```

**Chỉ có IP (cert tự ký):**
```bash
curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh \
  | sudo bash -s -- --domain 1.2.3.4
```

**Tuỳ chọn thêm** (gắn sau `--domain`):

| Cờ | Tác dụng |
|---|---|
| `--theme default` | (mặc định) Logo Tino + bảng màu xanh lá `#14a74b` |
| `--theme ictsaigon` | Logo iCTSAIGON + bảng màu xanh dương `#1E88E5` |
| `--skip-chrome` | Bỏ cài Chromium (tiết kiệm ~500 MB) |
| `--no-firewall` | Không cấu hình UFW |
| `--legacy-routing` | Caddy route `/` thẳng tới daemon (ẩn panel) |
| `--mgmt-key <KEY>` | Tự chỉ định API key thay vì để installer random |

Cài xong installer in `OPENCLAW_MGMT_API_KEY` ra màn hình — lưu vào password manager.

> **Trước khi chạy:** DNS A-record của domain phải trỏ về IP VPS, không thì Caddy không lấy được LE cert.

## Đổi theme sau khi đã cài

Sửa `/opt/openclaw/.env`:
```ini
OPENCLAW_THEME=default      # hoặc: ictsaigon
```
Rồi restart Management API:
```bash
sudo systemctl restart openclaw-mgmt
```

Refresh trình duyệt (Ctrl+Shift+R) để load HTML mới với theme đổi.

## Sau khi cài

1. Mở `https://<domain>/login` → đăng nhập bằng `OPENCLAW_MGMT_API_KEY` (tab "API Key") hoặc tài khoản admin
2. Vào `/ai-config` → chọn AI provider (Anthropic, OpenAI, Gemini, Mistral, …) → dán API key hoặc OAuth ChatGPT
3. Vào `/chat` → nhấn nút `+` để bắt đầu hội thoại
4. Đổi mật khẩu admin trong `/` → Tài khoản đăng nhập

## Tính năng

- **Chat AI thời gian thực**: theo dõi + gửi vào sessions của Opencrawl Gateway qua SSE
- **22 AI provider built-in**: Anthropic, OpenAI, OpenAI-Codex (OAuth), Gemini, Mistral, Groq, DeepSeek, Bedrock, Cohere, Azure, xAI, OpenRouter, Together, Fireworks, … + Custom OpenAI-compatible
- **OAuth ChatGPT/Codex**: PKCE flow, không cần API key
- **Multi-agent**: nhiều agent độc lập, mỗi agent có model + auth riêng
- **Self-update**: nâng cấp `openclaw` npm + Management API từ GitHub Releases ngay trong panel
- **Self-healing**: systemd timer kiểm tra cert / api / gateway / WS mỗi 5 phút, tự khôi phục
- **SSL Let's Encrypt** + **WAF rate-limit** + **CIDR whitelist** + **Bearer auth scrypt**
- **Terminal qua trình duyệt** (SSE PTY stream)
- **Log streaming** journald qua SSE
- **Domain pairing**: ghép thiết bị qua mã 60s
- **Theme switchable**: Tino mặc định, ICTSAIGON optional, đổi qua env không cần rebuild

## Local development

```bash
make install-dev      # python venv + npm install
make dev-api          # gunicorn :9998 với autoreload
make dev-ui           # vite dev server :5173 (proxy /api → :9998)
make test             # pytest (112 tests)
make build-ui         # vite build → static/dist/
make lint format      # ruff + black + mypy
```

Đặt `OPENCLAW_HOME=/tmp/openclaw-dev` để dev state không ghi vào `/opt`.

## Cấu trúc

```
openclaw-control-panel/
├── app/                Flask backend (factory + 13 blueprints + 20+ services)
│   ├── caddy/Caddyfile.template
│   ├── providers/      22 built-in + JSON template loader
│   ├── routes/         REST + SSE endpoints
│   └── services/       business logic, atomic .env writes
├── ui/                 React 18 SPA (Vite + Tailwind + shadcn)
│   ├── public/themes/  Brand assets (tino-logo.png, …)
│   └── src/index.css   Theme palettes keyed on html[data-theme=…]
├── tests/              pytest + integration + Playwright e2e
├── systemd/            4 unit + healthcheck timer
├── scripts/
│   ├── bootstrap.sh                One-liner downloader
│   ├── build-release-tarball.sh    Stage + tar.gz + sha256
│   ├── publish-github-release.sh   gh release create + upload
│   ├── openclaw-healthcheck.sh     5-min self-heal
│   ├── openclaw-sync-auth-profiles.sh
│   └── openclaw-config-enforce.sh
├── install.sh          Idempotent installer (450 dòng)
└── wsgi.py             gunicorn entrypoint
```

## API

56 endpoint REST + 2 SSE. Yêu cầu `Authorization: Bearer $OPENCLAW_MGMT_API_KEY` trừ `/api/health`, `/api/auth/login`, `/pair`.

## Cập nhật panel

Trong UI: `/version` → chọn phiên bản từ dropdown (có search + filter beta/stable) → "Nâng cấp OpenClaw" hoặc "Cập nhật Management API". Tarball pull từ GitHub Releases, swap atomic, restart service. Self-update fail-safe: nếu restart lỗi sẽ tự rollback config cũ.

Hoặc command-line:
```bash
sudo systemctl stop openclaw-mgmt
cd /tmp && curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/openclaw-panel.tar.gz -o new.tar.gz
sudo tar -xzf new.tar.gz -C /opt/openclaw-mgmt --strip-components=1
sudo systemctl start openclaw-mgmt
```

## License

MIT
