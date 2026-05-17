---
date: 2026-05-14
topic: Channels delete 25s + dangling bindings auto-recreating accounts
tags: [perf, bugfix, channels, bindings, hot-reload]
---

# Channels chậm + dangling bindings (3 bugs cascading)

User report: "Xoá 1 kênh telegram không được và load rất lâu." Đo: GET /api/channels = **9s** (lạnh), DELETE = **25s**. Cảm giác "không xóa được" thực ra là API timeout trước khi 25s xong.

## What happened

3 bug chồng lên nhau:

### Bug 1: GET /api/channels cold = 9s
`openclaw_channels_service.list_channels()` gọi `openclaw channels list --json` subprocess. Mỗi spawn openclaw CLI ~9s vì Node.js cold start + plugin loading + config validate. Cache 5s giúp warm calls nhưng cold load mỗi page nav = 9s.

**Fix**: Đọc trực tiếp từ shared `.openclaw/openclaw.json` (`openclaw_config_service.read()`). Cache 5s vẫn giữ cho repeat-render. **9s → 13ms (700×)**.

### Bug 2: DELETE = 25s
`channels_routes.py` gọi `openclaw_channels_service.remove_account()` (gọi CLI `openclaw channels remove --delete` = ~19s) + `systemd_service.restart("openclaw")` (~6s). Tổng 25s.

**Fix**: 
- Skip `systemd_service.restart()` — shared config = hot-reload đủ (panel write → openclaw watcher → "restarting telegram channel" sau ~200ms).
- Write trực tiếp config thay vì CLI: `cfg["channels"][channel]["accounts"].pop(account_id)` → write_atomic. CLI cũng tránh `ConfigMutationConflictError` khi gateway cached stale config.
- **25s → 39ms (640×)**.

### Bug 3: Dangling bindings recreate "ma accounts"
User báo "đã xóa bot2 mà vẫn thấy". Investigation: live config chỉ có bot1, nhưng `openclaw channels list` trả về `bot1 + bot2 + default`. Crash loop `[default] auto-restart attempt N/10`.

Root cause: `bindings` array trong config vẫn reference bot2 + default mặc dù 2 accounts này đã xóa khỏi `channels.telegram.accounts`. OpenClaw quét bindings, thấy reference đến `accountId: bot2`, **tự instantiate** một provider ảo cho bot2 — không có token → 404 deleteWebhook → crash → auto-restart cycle.

**Fix**: Trong `remove_account` route, sau khi xóa account, prune bindings có `match.accountId == account_id` (cùng channel). Return `bindings_removed: N` trong response để UI hiển thị.

```python
def _prune_dangling_bindings(channel: str, account_id: str) -> int:
    cfg = read()
    bindings = cfg.get("bindings", [])
    kept = [b for b in bindings if not (
        b.get("match",{}).get("channel") == channel and
        b.get("match",{}).get("accountId") == account_id
    )]
    if len(bindings) != len(kept):
        cfg["bindings"] = kept
        write_atomic(cfg)
    return len(bindings) - len(kept)
```

## Verification

```
POST /api/channels/telegram/accounts (bot-temp3) → 0.039s (was 6s)
POST /api/bindings (agent2 → telegram:bot-temp3) → 0.041s
GET /api/channels → instant (no subprocess)
DELETE /api/channels/telegram/accounts/bot-temp3 → 0.039s,
  bindings_removed: 1 (binding agent2→bot-temp3 auto-pruned)
Final state: 1 account (bot1), 0 dangling bindings, no crash loop.
```

## Decisions / lessons

- **Cold subprocess là tax ẩn**: 9s mỗi page load là không acceptable. Khi shared state file có sẵn, đọc trực tiếp.
- **`systemd restart` là sledgehammer trong shared-config setup**: hot-reload đã handle, restart chỉ thêm 6-10s downtime + reset memory state.
- **`ConfigMutationConflictError` của openclaw**: CLI client cache snapshot của config khi load. Nếu file thay đổi giữa load và write, CLI từ chối. Khi panel + openclaw cùng write file, CLI dễ conflict. → Skip CLI cho mutations, đi thẳng config file.
- **Dangling refs = ma accounts**: OpenClaw không validate cross-section (binding ⇄ channel account). Nó tự "fill in" account thiếu bằng cách instantiate provider ảo. Panel phải tự enforce referential integrity.
- **API timeout > error**: User "không xóa được" thực ra là fetch timeout. Browser default timeout cho fetch không có, nhưng UI hiển thị "loading" lâu → user reload page → state inconsistent. Fast operations > robust error handling.

## Files touched

- `app/services/openclaw_channels_service.py` — `list_channels`/`add_account`/`remove_account` switched to direct config write
- `app/routes/channels_routes.py` — removed `systemd_service.restart()`; added `_prune_dangling_bindings()` helper; `bindings_removed` in response

## Open questions

- `botToken` ở parent level (legacy schema) bị openclaw doctor tự re-add. Có nên override behavior này từ panel?
- Khi user add custom field không trong SUPPORTED_CHANNELS schema, có nên drop hay forward?
- `_prune_dangling_bindings` chỉ chạy khi delete account. Có nên có cleanup periodic cho orphans phát sinh từ source khác (e.g., user edit config thủ công)?
