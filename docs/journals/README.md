# Technical Journals

Honest technical reflections — what happened, what was decided, what went wrong, lessons learned. Sacrifice grammar for concision.

## 2026-05-14 — Production deploy + iteration day

Project port (12 phases, 117 tests) đã xong từ trước. Hôm nay: deploy lên VPS demo thật + iterate theo user feedback.

| Entry | TL;DR |
|-------|-------|
| [vps-deploy-billionmail-conflict](260514-vps-deploy-billionmail-conflict.md) | install.sh chạy clean trên Ubuntu 22.04 demo VPS. Caddy fail vì BillionMail Docker chiếm 80/443. Stop 1 container `billionmail-core` → Caddy + Let's Encrypt up trong 3s. |
| [vietnamese-spa-rewrite](260514-vietnamese-spa-rewrite.md) | User gửi screenshots panel cũ → rewrite full SPA: 9 routes Vietnamese, light/green theme, thêm Chat AI tab gọi `openclaw capability model run`. |
| [openclaw-gateway-ui-origin-saga](260514-openclaw-gateway-ui-origin-saga.md) | 5+ giờ debug OpenClaw Control UI qua Caddy reverse proxy. 11 approaches. Final: Caddy `:18790` + `header_up Origin "http://localhost:18789"` + manual `devices approve` + URL fragment `#token=`. |
| [multi-account-telegram-bug-chain](260514-multi-account-telegram-bug-chain.md) | Multi-bot Telegram + agent routing. Bug chain: HTTP 400 (wrong CLI flag) → schema divergence (panel writes legacy, openclaw uses live) → fake token `121212` crash loop blocking bot2 polling. Fix: wrap `openclaw channels/agents/bindings` CLI từ panel. |
| [config-divergence-binding-schema](260514-config-divergence-binding-schema.md) | Post-deploy hardening. Panel reads `/config/openclaw.json` vs openclaw uses `/.openclaw/openclaw.json` → demo-agent ảo. Unify path. Binding `description` field bị schema reject. UI `account` vs `accountId` mismatch. Caddy `lb_try_duration` cho transient 502. |
| [channels-slow-and-dangling-bindings](260514-channels-slow-and-dangling-bindings.md) | GET 9s → 13ms, DELETE 25s → 39ms (direct config write, skip systemd restart). Dangling bindings ref `bot2`/`default` đã xóa → openclaw tự instantiate "ma accounts" → crash loop. Fix: prune bindings khi xóa account. |

## Cross-cutting themes

1. **OpenClaw npm package được design cho local-loopback + SSH-tunnel**, không phải public reverse-proxy. Mọi guard (origin, host header, device pairing) cộng dồn chống lại pattern public exposure.
2. **Schema divergence panel ⇄ openclaw**: hai hệ thống quản lý cùng key (agents, bindings, channels accounts) với schema khác. Cần wrap CLI, KHÔNG tự ghi JSON.
3. **5s cache trên CLI subprocess** — sweet spot cho admin operations (UI không cần realtime ms).
4. **`dangerously*` flags không thực sự disable** mọi check ở openclaw — dev nên đọc source khi flag không effect.
