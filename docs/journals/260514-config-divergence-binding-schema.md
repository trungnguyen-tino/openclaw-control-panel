---
date: 2026-05-14
topic: Panel ⇄ openclaw config divergence + binding schema rejection
tags: [bugfix, schema, config, multi-agent, bindings]
---

# Config divergence + binding schema (post-deploy hardening)

User asked: "Tiếp tục debug các lỗi khác đảm bảo panel openclaw này hoàn động hoàn hảo" — find/fix every remaining bug after the Telegram crisis. Found a bigger structural bug below the surface.

## What happened

1. **Panel + openclaw đọc 2 file khác nhau.** Panel ghi `/opt/openclaw/config/openclaw.json`; openclaw npm ghi `/opt/openclaw/.openclaw/openclaw.json`. Sau khi multi-account flow đã wrap CLI cho **mutations**, READ vẫn divergent: `/api/agents` trả `demo-agent` trong khi runtime có `main + agent2`.

2. **Trigger phát hiện:** `journalctl -u openclaw-mgmt` báo `openclaw agents delete failed: Non-interactive session. Re-run with --force.` — fix nhanh (thêm `--force`), nhưng bới ra divergence root cause.

3. **Unify approach:** Add `OPENCLAW_CONFIG_FILE` env override, default đổi sang `.openclaw/openclaw.json`. Atomic write (`os.replace`) sẽ break symlink → buộc phải đổi đường dẫn thật, không symlink.

4. **Sau khi unify, binding API fail "Config invalid: bindings.1: Invalid input"**. So sánh entry panel-written vs CLI-written: panel có thừa field `description: "..."`. OpenClaw zod schema reject extra fields.

5. **Bug nhỏ trong UI:** `multi-agent.tsx` đọc `match.account` (✗) thay vì `match.accountId` (✓) → table hiển thị `*` thay vì `bot2` cho binding telegram→agent2.

6. **Side effect của unify:** Sau khi panel chuyển sang đọc live config, `agents.defaults` (model.primary) biến mất → chat fail "No active provider/model". Phải merge defaults từ panel backup vào live config + `openclaw doctor --fix`.

## Decisions / lessons

- **Khi 2 hệ thống cùng quản key, đừng duplicate** — chia sẻ file là cách duy nhất tránh drift dài hạn. Wrap CLI là band-aid; root cause là 2 nguồn truth.
- **Atomic write phá symlink.** `os.replace(tmp, target)` xóa symlink. Không dùng symlink để unify path; thay đổi path config thẳng.
- **OpenClaw schema strict-extra**. Mọi extra field bị reject. Không tự ý thêm `description`, `note`, etc. vào binding entry — chỉ ghi đúng các key openclaw expect: `type`, `agentId`, `match`.
- **UI/API field name sync** — backend đã normalize `account` → `accountId`, nhưng UI vẫn dùng tên cũ. Sau khi đổi field, search both sides (read + write) cho mọi component.
- **Provider switch không tạo `models.providers.<id>`** — template chỉ có gateway/browser/agents.defaults. OpenClaw routing bằng env var `OPENAI_API_KEY` đủ cho built-in; `models` block chỉ cần khi custom routing.
- **Loại bỏ CLI calls khi shared config**: `agents add/delete` và `agents bind/unbind` redundant — panel write trigger hot-reload, openclaw thấy ngay. CLI vẫn được gọi từng làm noise log "already exists" / "not found".

## Files touched

- `app/config.py` — `config_file = os.environ.get("OPENCLAW_CONFIG_FILE", home / ".openclaw" / "openclaw.json")`
- `app/services/agent_service.py` — drop `_register_with_openclaw` / `_unregister_from_openclaw` CLI wrappers; write `workspace` + `agentDir` directly trong panel entry
- `app/services/bindings_service.py` — drop CLI bind/unbind; write strict `{type, agentId, match}` entries; normalize `accountId`
- `ui/src/routes/multi-agent.tsx` — `match.account` → `match.accountId` (cả interface, write, read)
- `tests/conftest.py` — tạo `.openclaw/` dir trong tmp tree (test compat)
- VPS `/opt/openclaw/Caddyfile` — thêm `lb_try_duration 15s` cho transient 502 khi openclaw restart

## Verification

```bash
# E2E test (curl)
POST /api/agents {id: e2e2} → panel + openclaw đều thấy agent2 + workspace/agentDir
POST /api/bindings {agentId: e2e2, match: {channel: telegram, accountId: bot2}}
  → panel ghi 1 entry, openclaw bindings list trả 1 entry tương ứng (KHÔNG duplicate)
DELETE /api/bindings/1 + DELETE /api/agents/e2e2 → cleanup sạch

# UI test (Playwright)
multi-agent table: row "0 telegram bot2 agent2 🗑" — accountId hiển thị đúng
chat: gpt-4o-mini phản hồi "OK" qua gateway
logs page: 3 services (OpenClaw, Caddy, Management API)

# Final health
3 services active. 0 errors trong 5 min log. Bot @decuatrung_bot polling clean.
```

## Emotional note

Patterns lặp lại: mỗi lần discover một bug nhỏ, đào xuống lại là một bug structural lớn hơn. `--force` flag → divergence → schema strict → UI field mismatch → defaults missing. Mỗi fix unwrap thêm một layer. Hôm nay 4 layer xuống, panel mới thực sự "hoàn động hoàn hảo".

Cảm giác hết — vì các fix giờ là kết quả của hiểu hệ thống (shared config = source of truth) chứ không phải hack riêng lẻ. Trust được code lâu hơn.

## Open questions

- `openclaw doctor --fix` overwrote 13 path. Có path nào trong số đó liên quan auth/security mà ta cần re-verify?
- `models.providers.<id>` để trống vẫn route được vì env var. Khi user thêm custom provider/baseUrl, có cần generate `models.providers` block không?
- Provider template `agents.defaults.model.primary = "openai/gpt-5.2"` — tại sao default lại là 5.2 (không tồn tại trong known_models)? Test merge có override đúng không?
