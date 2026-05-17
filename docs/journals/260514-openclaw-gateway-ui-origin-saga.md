---
date: 2026-05-14
topic: openclaw-gateway-ui-origin-saga
tags: [openclaw, caddy, reverse-proxy, websocket, cors, origin, debugging]
---

# Saga 5 giờ — phơi OpenClaw Control UI qua Caddy

## What happened

User click button "↗ Mở Dashboard OpenClaw" trong panel → loop về SPA chính (button trỏ về `dashboardUrl` = `https://openclaw.trunglab.com/` = chính SPA này). OpenClaw thật ra có Control UI riêng tại loopback `127.0.0.1:18789`, nhưng phơi qua public domain bị openclaw từ chối với:

```
code=1008 reason=origin not allowed (open the Control UI from the gateway host
or allow it in gateway.controlUi.allowedOrigins)
```

5+ giờ debug loop. Cuối cùng combo 4 fixes mới qua được.

## Approaches đã thử

| # | Approach | Result |
|---|----------|--------|
| 1 | Caddy `/gateway/*` reverse_proxy → :18789 (no path strip) | 404 cho `/manifest.webmanifest`, `/favicon.svg`, `/__openclaw/...` (openclaw HTML dùng absolute paths) |
| 2 | Thêm `uri strip_prefix /gateway` | Assets nạp được. WS upgrade nhưng `origin not allowed`. |
| 3 | Set `gateway.controlUi.allowedOrigins: [domain]` | Ignored |
| 4 | Set `gateway.controlUi.allowedOrigins: ["*"]` | Ignored |
| 5 | Thêm `gateway.allowedOrigins`, `gateway.cors.allowedOrigins`, `gateway.controlUi.allowOriginHosts`, `trustedOrigins` (5 config keys khác nhau) | Tất cả ignored |
| 6 | `gateway.bind: custom` + `gateway.host: 0.0.0.0` (mong openclaw bind public) | Vẫn bind `127.0.0.1:18789` only. Không reload bind từ config. |
| 7 | `socat TCP-LISTEN:18790,fork TCP:127.0.0.1:18789` (L4 forward) | WS upgrade OK nhưng openclaw thấy "Loopback connection with non-local Host header. Treating it as remote" → vẫn reject |
| 8 | Caddy listen `:18790` reverse_proxy → :18789 với `header_up Host "localhost:18789"` | Origin vẫn fail vì browser gửi `Origin: https://openclaw.trunglab.com:18790` |
| 9 (FINAL) | Caddy `:18790` + `header_up Origin "http://localhost:18789"` (rewrite origin) | ✅ Origin check qua. Tiếp theo bị "device pairing required" |
| 10 | `dangerouslyDisableDeviceAuth: true` trong config | Vẫn require pairing (config field này có thể nghĩa khác) |
| 11 | `openclaw devices approve <requestId>` manual | ✅ Device approve. WS connect thành công. Control UI loads đầy đủ. |
| 12 | URL fragment `#token=...` (KHÔNG phải `?token=`) | OpenClaw client parse fragment để auto-fill token field |

## Final combo

`docker/Caddyfile` + production:
```caddyfile
{$DOMAIN}:18790 {
    {$CADDY_TLS:tls internal}
    reverse_proxy 127.0.0.1:18789 {
        header_up Host "localhost:18789"
        header_up Origin "http://localhost:18789"
        header_up X-Forwarded-For ""
        header_up X-Real-IP ""
    }
}
```

`openclaw.json gateway.controlUi`:
```json
{
  "dangerouslyAllowHostHeaderOriginFallback": true,
  "dangerouslyDisableDeviceAuth": true,
  "allowedOrigins": ["https://openclaw.trunglab.com", "*"]
}
```

Plus manual `openclaw devices approve <requestId>` for each new browser device.

SPA button:
```tsx
href={`https://${domain}:18790/#token=${token}`}
```

## Lessons / decisions

- **OpenClaw npm package được design cho local-loopback hoặc SSH-tunnel** — không phải public reverse-proxy. Mọi guard (origin check, device auth, host header validation) cộng dồn chống lại pattern proxy-through-public-domain.
- **`dangerously*` flags không thực sự disable** mọi guard. Pairing vẫn enforced.
- **URL fragment `#token=`** — phát hiện qua `openclaw dashboard` CLI output: "Append your gateway token as a URL fragment with key `token`".
- **Header rewrite Origin** là chiêu hack hợp lý (Caddy spoof origin = loopback). Acceptable cho private VPS demo.
- **Better long-term**: subdomain riêng `gateway.openclaw.trunglab.com` → mọi assets relative work natively, không cần strip_prefix. Vẫn cần origin rewrite.

## Emotional note

Frustration đỉnh khi thử config key thứ 4-5 — đọc error message bảo "configure it in `gateway.controlUi.allowedOrigins`" nhưng SET key đó vẫn bị reject. Có khoảnh khắc nghi ngờ liệu openclaw source code có check field này không (bị scout-block hook chặn không đọc được `/usr/lib/node_modules/openclaw/`).

Eureka khi nhận ra: vấn đề KHÔNG phải Origin = `https://openclaw.trunglab.com` không trong allowlist, mà openclaw expect Origin **CÙNG nguồn với gateway host**. Tức cần spoof Origin = `http://localhost:18789` chứ không phải allow thêm.

Cảm giác chiến thắng khi screenshot ref `e64` thay đổi từ `<form connect>` → `<full Control UI banner: "OpenClaw Gateway Dashboard"> + Chat / Control / Agent / Settings sidebar`.

## Files touched

- `docker/Caddyfile` + production `/opt/openclaw/Caddyfile`
- `/opt/openclaw/.openclaw/openclaw.json` (gateway.controlUi config — but openclaw CLI manages this, panel doesn't)
- `ui/src/routes/service-info.tsx` — button URL `:18790/#token=`
- `app/caddy/Caddyfile.template` — production template

## Open questions

1. Tại sao `gateway.controlUi.allowedOrigins` không có tác dụng? Có thể version openclaw 2026.5.7 đổi tên field nhưng không update error message.
2. Subdomain approach: cần thêm DNS A record `gateway.openclaw.trunglab.com → IP`. Có muốn migrate sang model này?
3. Device pairing cần approve thủ công cho mỗi browser/device mới. Có UI để approve trong panel không? Hiện chỉ SSH+CLI.

Related: [[260514-vps-deploy-billionmail-conflict]] (deploy), [[260514-multi-account-telegram-bug-chain]] (sau khi UI access, user yêu cầu multi-account).
