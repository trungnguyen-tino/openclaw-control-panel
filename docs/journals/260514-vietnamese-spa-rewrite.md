---
date: 2026-05-14
topic: vietnamese-spa-rewrite
tags: [spa, vietnamese, ui-rewrite, tailwind, chat]
---

# SPA full rewrite: English-dark → Vietnamese-light + Chat AI

## What happened

Sau khi deploy production, user gửi 8 screenshots của một panel cũ — UI tiếng Việt, light theme, green accent, 8 sidebar items dạng:
- Thông tin dịch vụ / Tên miền & SSL / Cấu hình AI / Multi-Agent / Kênh kết nối / Phiên bản & Nâng cấp / Nhật ký hệ thống / Điều khiển dịch vụ

Yêu cầu rebuild SPA của ta để match design này (user đã quen từ Docker-based panel cũ tại `trungopenclaw.tino.page`).

Plus: user hỏi "làm sao bắt đầu chat?" — phát hiện OpenClaw thiết kế cho **channels** (Telegram/Discord/etc), không có chat-box built-in trong panel. User chọn thêm Chat AI tab.

## Decisions / lessons

**Theme switch (`ui/src/index.css`)**:
- HSL primary từ neutral → green `142 70% 35%`
- Light defaults: background `210 30% 98%`, foreground `222 47% 11%`
- Remove `class="dark"` từ `<html>` → mặc định light

**Sidebar restructure (`ui/src/components/layout/AppShell.tsx`)**:
- 9 items thay vì 9 cũ (gộp khác): Thông tin / Chat AI / Tên miền / Cấu hình AI / Multi-Agent / Kênh / Phiên bản / Nhật ký / Điều khiển
- Vietnamese labels + icon emoji
- Active item: bg accent + border-l-2 primary

**8 trang Vietnamese mới** (`ui/src/routes/*.tsx`):
- `service-info.tsx` thay `dashboard.tsx` — gateway token với eye/regenerate + login user card
- `domain.tsx` — DNS warning banner xanh
- `ai-config.tsx` — providers + custom + ChatGPT OAuth gộp 1 trang
- `multi-agent.tsx` — agents + bindings gộp
- `channels.tsx` — 4 cards (lần 1, sau mở rộng 6 ở entry [[260514-multi-account-telegram-bug-chain]])
- `version.tsx` — upgrade + self-update
- `logs.tsx` — terminal-style log viewer + SSE
- `control.tsx` — restart/stop + danger zone reset
- Xoá 7 routes cũ (dashboard, providers, agents, bindings, devices, terminal, settings)

**Chat AI mới (`app/services/chat_service.py` + `app/routes/chat_routes.py`)**:
- `POST /api/chat {message, model?}` → spawn `openclaw capability model run --gateway --json`
- Parse JSON output → return `{ok, text, model, provider, transport}`
- Rate-limit 20/min
- SPA `routes/chat.tsx`: chat box giao diện ChatGPT-like, mỗi turn độc lập (không context)

**Build verification**:
- Tarball mới 137 KB (v1.1.0-vn)
- npm build clean: 30 KB gzip JS bundle
- Đầu lỗi: TypeScript implicit-any do `useQuery` v5 không infer type → fix bằng explicit `(a: AgentRow) =>`
- @tanstack/react-query thiếu trong package.json (quên thêm khi viết App.tsx). Phải `npm install @tanstack/react-query@5`.

**Test live cuối**:
- Login admin/DemoPass2026 → Service Info Vietnamese
- Chat AI tab → "Xin chào! 1+1 bằng mấy?" → `"1 + 1 bằng 2."` từ openai/gpt-4o-mini

## Emotional note

User rất specific về visual design — phải làm đúng. Cảm giác như viết lại từ đầu thay vì refactor. Đỡ khi build clean lần đầu + Vietnamese render đẹp trong browser.

Pleasantly surprised khi chat AI thật sự hoạt động trên prod — thấy GPT-4o-mini trả lời tiếng Việt chuẩn cú pháp.

## Files touched

Frontend:
- `ui/src/components/layout/AppShell.tsx`
- `ui/src/App.tsx`
- `ui/src/index.css`, `ui/index.html`, `ui/tailwind.config.js`
- `ui/src/components/ui/Button.tsx` (thêm `asChild` + `secondary`/`icon` variants)
- 9 new files: `ui/src/routes/{service-info,chat,domain,ai-config,multi-agent,channels,version,logs,control}.tsx`
- Removed: 7 routes cũ

Backend:
- `app/services/chat_service.py` (mới)
- `app/routes/chat_routes.py` (mới)
- `app/__init__.py` (register chat_bp)
- `tests/test_endpoint_contract.py` (thêm /api/chat)

Tests vẫn 117 pass.

## Open questions

1. Chat AI không có context giữa các turn — có nên thêm session memory bằng cách persist messages backend?
2. Mỗi chat call subprocess `openclaw capability model run` ~10s — chậm. Có cách stream qua SSE tốt hơn không?
3. Theme switcher (light/dark toggle) hiện chưa có — user chỉ muốn light. Skip.

Related: [[260514-vps-deploy-billionmail-conflict]] (deploy trước rồi mới rewrite UI), [[260514-openclaw-gateway-ui-origin-saga]] (sau khi rewrite, user click button "Mở Dashboard OpenClaw" và phát hiện issue origin).
