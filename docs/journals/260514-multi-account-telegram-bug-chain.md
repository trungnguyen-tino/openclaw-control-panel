---
date: 2026-05-14
topic: multi-account-telegram-bug-chain
tags: [multi-account, telegram, openclaw-cli, bug-chain, routing, debugging]
---

# Multi-account Telegram — chuỗi bug từ schema → CLI flag → routing

## What happened

User hỏi: "Hiện tại chỉ hỗ trợ 4 kênh, tôi muốn nhiều agents + nhiều Telegram bot bind đến từng agent được không?"

Khám phá: OpenClaw npm 2026.5.7 **HỖ TRỢ NATIVE** multi-account qua `openclaw channels add --account <id>`. 23 channels khả dụng (telegram/discord/slack/whatsapp/matrix/zalo/+17 nữa). Plus `openclaw agents add <id>` + `openclaw agents bind --bind channel:account` để route.

User chọn full rebuild với 6 popular channels.

Build xong. User test → 3 bugs liên tiếp:

## Bug chain

### Bug 1 — HTTP 400 khi save bot2

User add Telegram account `bot2` với Bot Token thật từ @BotFather → HTTP 400.

Log openclaw:
```
Telegram requires token or --token-file (or --use-env).
```

**Root cause**: tôi map `bot_token` → CLI flag `--bot-token` (theo `add --help` output). Nhưng Telegram channel cụ thể yêu cầu `--token` (generic). Discord cũng tương tự.

**Fix**: đổi schema `cli: "--bot-token"` → `cli: "--token"` cho telegram/discord/slack/zalo. Matrix giữ `--access-token`. WhatsApp giữ `--http-url`.

### Bug 2 — agent2 không nhận được message

User tạo agent2 + binding telegram:bot2 → agent2 qua panel. Mọi thứ "success" UI nhưng:
- Screenshot OpenClaw Control UI → tab "Agent" chỉ có `main (default)` — KHÔNG thấy agent2
- "hello" nhắn bot → không phản hồi

**Root cause**: Panel ghi `agents.list` + `bindings` vào `/opt/openclaw/config/openclaw.json` (legacy schema). Nhưng openclaw npm thực ra dùng `/opt/openclaw/.openclaw/openclaw.json` (file ĐÃ DIVERGED khỏi symlink gốc). Đây là 2 file khác hash MD5.

Schema mới của openclaw:
```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "accounts": {
        "bot2": {"name": "bot2", "enabled": true, "botToken": "8250..."}
      }
    }
  },
  "agents": {"list": [{"id": "main"}, {"id": "agent2", "workspace": "..."}]},
  "bindings": [{"type": "route", "agentId": "agent2", "match": {"channel": "telegram", "accountId": "bot2"}}]
}
```

Panel viết schema cũ → openclaw không thấy.

**Fix**: extend `agent_service.create_agent` + `bindings_service.append_binding` để **gọi thêm CLI**:
- `openclaw agents add <id> --workspace <path> --agent-dir <path> --non-interactive --json`
- `openclaw agents bind --agent <id> --bind <channel>[:<account>] --json`

Plus mirror cho delete: `openclaw agents delete` + `openclaw agents unbind`.

Sync 2 chiều giờ ổn: panel state cho UI tracking, openclaw CLI cho live routing.

### Bug 3 — "hello" vẫn không phản hồi sau Bug 2 fix

Log openclaw mỗi 11-88s:
```
[telegram] [default] channel exited: Call to 'deleteWebhook' failed! (404: Not Found)
[telegram] [default] auto-restart attempt 5/10 in 88s
```

**Root cause**: account `default` của telegram có token rỗng / fake `121212` (từ legacy `.env: TELEGRAM_BOT_TOKEN=121212` của user lúc test ban đầu). Telegram channel plugin start TẤT CẢ accounts cùng lúc → default crash → block bot2 polling.

**Fix**: `openclaw channels remove --channel telegram --account default --delete`. Hot-reload qua openclaw `[reload] config change detected`. Bot2 then started cleanly: `[telegram] [bot2] starting provider (@decuatrung_bot)`.

Test: `openclaw agent --agent agent2 -m "ping" --json` → real openai/gpt-5.5 response.

### Bonus issue — /channels page load chậm

User notice `/channels` load 8.5s. Backend mỗi request subprocess `openclaw channels list --json` ~5-8s.

**Fix**: thêm 5s TTL cache trong `openclaw_channels_service.list_channels()`. Mutation (add/remove) invalidate cache → state luôn cập nhật.

- First call cold: 8.5s
- Second call warm: 0.13s (**65× faster**)

## Lessons / decisions

- **Schema sync giữa panel ⇄ openclaw**: hai system quản lý cùng key (agents.list, bindings, channels) nhưng schema khác nhau. Wrap CLI là cách duy nhất giữ consistent — không "tự ghi JSON".
- **Symlink `.openclaw` → `config`** không bền: install.sh tạo symlink, nhưng `openclaw agents add` hay `agents bind` ghi materialize ra real dir. Sau đó panel ghi `config/` còn openclaw ghi `.openclaw/` → diverge silently.
- **`channels remove` cleanup quan trọng**: legacy accounts với fake token tiếp tục crash loop, ảnh hưởng cả channel. UI cần show status per account.
- **CLI flag names khác per-channel**: `add --help` show `--bot-token` nhưng Telegram cụ thể đòi `--token`. Documentation gap trong openclaw.
- **Cache TTL 5s** là sweet spot: state vẫn near-real (admin operation không cần realtime millisecond), tránh subprocess 5-8s mỗi request.

## Emotional note

Bug 1 ngắn (15 phút). Bug 2 đào sâu — phải đọc full openclaw.json để hiểu schema divergence, "aha" moment khi md5sum hai file khác nhau. Bug 3 frustration cao nhất: 30 phút tìm tại sao bot không reply dù routing đã đúng. Khi thấy log "default auto-restart attempt 5/10" → smile + facepalm: user nhập token `121212` từ lúc test đầu.

Cảm giác cuối khi `openclaw agent --agent agent2 -m "ping"` trả về paragraph từ gpt-5.5 — "agent2 đã thật sự sống".

## Files touched

Backend:
- `app/services/openclaw_channels_service.py` (mới) — wrap channels CLI + 5s cache
- `app/services/agent_service.py` — thêm `_register_with_openclaw`, `_unregister_from_openclaw`, call vào create/delete
- `app/services/bindings_service.py` — thêm `_openclaw_bind/_openclaw_unbind`, call vào append/delete
- `app/routes/channels_routes.py` — endpoints `POST /<ch>/accounts`, `DELETE /<ch>/accounts/<id>`, schema endpoint
- `app/routes/__init__.py` (register chat_bp tiếp tục)

Frontend:
- `ui/src/routes/channels.tsx` (rewrite full) — 6 cards, accounts list, dynamic form từ `/api/channels/schema`, edit account inline
- `ui/src/routes/multi-agent.tsx` — bindings với account dropdown (filtered theo channel)

Tests:
- `tests/test_endpoint_contract.py` — thêm `/api/channels/schema`, `/api/channels/<ch>/accounts`, `/api/channels/<ch>/accounts/<id>`
- `tests/test_channels.py` — rewrite cho multi-account + stub openclaw_channels_service

120 tests pass.

## Open questions

1. Symlink `.openclaw` đã broken. Có nên restore? Sẽ phải migrate state hiện tại từ `.openclaw/` → `config/` nếu khôi phục symlink hoặc ngược lại.
2. UI chưa show **status** per account (online/offline). Cần `openclaw channels status` integration.
3. Pairing flow: openclaw require approve mỗi user lần đầu nhắn bot. Hiện phải SSH chạy `openclaw pairing approve`. Cần UI để approve.
4. Cleanup function: khi user remove account qua panel, có chắc openclaw cleanup hết state (allowFrom, sessions)?
5. Account ID hiện chỉ accept `[a-z0-9-_]` lowercase. Case-insensitive?

Related: [[260514-vietnamese-spa-rewrite]] (rewrite UI trước), [[260514-openclaw-gateway-ui-origin-saga]] (sau khi xong multi-account, các trang UI khác đã work, chỉ Gateway Control UI cần saga riêng).

## Stats cuối session

- Code: 120 pytest tests pass
- Live: openclaw.trunglab.com production với SPA Vietnamese + Chat AI + multi-account Telegram (1 bot real: @decuatrung_bot bound agent2)
- Total session: ~4h từ deploy đến bot phản hồi qua agent2
- Bugs: 3 chain bugs + 1 perf issue, mỗi cái ~30 phút root cause
