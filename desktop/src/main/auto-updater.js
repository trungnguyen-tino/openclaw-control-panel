// Auto-update wiring around electron-updater.
//
// Behaviour (optimal default — no questions asked):
//   - Check for updates 30s after launch (give the user time to see the
//     tray icon settle), then every 6h while the app stays open.
//   - Download new versions silently in the background.
//   - When a download finishes, the tray menu surfaces a "Khởi động lại
//     để cập nhật" item; clicking installs + relaunches.
//   - All download errors are swallowed into the log file — no popups —
//     so a broken network never blocks the app.
//
// Skipped entirely when:
//   - app.isPackaged === false (dev mode, no installer)
//   - settings disabled the feature in the future (placeholder hook)

"use strict";

const { app, autoUpdater: _builtin } = require("electron");
const log = require("node:console");

let _updater = null;
let _state = "idle"; // "idle" | "checking" | "available" | "downloading" | "downloaded" | "error"
let _onUpdate = () => {};

function _tryLoad() {
  if (_updater) return _updater;
  try {
    // Lazy require so dev mode without the dep installed still boots.
    _updater = require("electron-updater").autoUpdater;
  } catch (err) {
    log.warn("electron-updater not available:", err.message);
    return null;
  }
  return _updater;
}

function setupAutoUpdater({ onUpdate } = {}) {
  if (typeof onUpdate === "function") _onUpdate = onUpdate;
  if (!app.isPackaged) return; // dev mode — skip
  const u = _tryLoad();
  if (!u) return;

  // Quiet defaults: no popups, no logger override (leave to electron-updater).
  u.autoDownload = true;
  u.autoInstallOnAppQuit = true;
  u.allowDowngrade = false;

  u.on("checking-for-update", () => {
    _state = "checking";
    _onUpdate();
  });
  u.on("update-available", () => {
    _state = "available";
    _onUpdate();
  });
  u.on("update-not-available", () => {
    _state = "idle";
    _onUpdate();
  });
  u.on("download-progress", () => {
    _state = "downloading";
    _onUpdate();
  });
  u.on("update-downloaded", () => {
    _state = "downloaded";
    _onUpdate();
  });
  u.on("error", (err) => {
    log.error("auto-update error:", err?.message ?? err);
    _state = "error";
    _onUpdate();
  });

  // Stagger: 30s after launch, then every 6h.
  setTimeout(() => u.checkForUpdates().catch(() => {}), 30_000);
  setInterval(() => u.checkForUpdates().catch(() => {}), 6 * 60 * 60 * 1000);
}

function _label() {
  switch (_state) {
    case "checking":
      return "Đang kiểm tra cập nhật…";
    case "available":
      return "Có bản cập nhật — đang tải…";
    case "downloading":
      return "Đang tải bản cập nhật…";
    case "downloaded":
      return null; // surfaced as a separate clickable item
    case "error":
      return "Cập nhật: lỗi (sẽ thử lại sau)";
    default:
      return null;
  }
}

function getUpdateMenuItems() {
  if (!app.isPackaged) {
    return [{ label: "Cập nhật: dev mode (tắt)", enabled: false }];
  }
  const items = [];
  const text = _label();
  if (text) items.push({ label: text, enabled: false });
  if (_state === "downloaded") {
    items.push({
      label: "Khởi động lại để cập nhật",
      click: () => {
        const u = _tryLoad();
        if (u) u.quitAndInstall(false, true);
      },
    });
  } else if (_state === "idle") {
    items.push({
      label: "Kiểm tra cập nhật ngay",
      click: () => {
        const u = _tryLoad();
        if (u) u.checkForUpdates().catch(() => {});
      },
    });
  }
  return items;
}

module.exports = { setupAutoUpdater, getUpdateMenuItems };
