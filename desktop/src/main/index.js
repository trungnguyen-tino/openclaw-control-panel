// Electron entry point — Architecture B (WSL2 backend bridge).
//
// Responsibilities:
//   - Enforce single-instance (only one tray icon ever).
//   - Show first-run wizard until BootstrapRunner reports DONE.
//   - After ready, expose a tray icon with: Open Panel / Settings / Quit.
//   - Lazy-create the BrowserWindow that loads http://127.0.0.1:9998
//     (WSL2 auto-forwards localhost across the boundary).
//   - Persist user settings — auto-start with Windows, auto-open-window
//     on launch — under app.getPath("userData").
//
// Heavy work (WSL/bootstrap orchestration) lives in sibling modules so
// this file stays a coordinator, not a do-everything controller.

"use strict";

const { app, Tray, Menu, BrowserWindow, ipcMain, shell, clipboard, nativeImage } =
  require("electron");
const path = require("node:path");
const fs = require("node:fs");

const { BootstrapRunner, Step } = require("./bootstrap-runner");
const { CloudflaredManager, State: TunnelState } = require("./cloudflared-manager");

const PANEL_URL = "http://127.0.0.1:9998";
const TRAY_ICON = path.join(__dirname, "../../resources/tray.png");
const SETTINGS_FILE = path.join(app.getPath("userData"), "settings.json");

const tunnel = new CloudflaredManager({ app });

// ─── Settings ─────────────────────────────────────────────────────────────

const DEFAULT_SETTINGS = Object.freeze({
  autoStart: true, // launch when Windows boots
  openWindowOnStart: false, // …but stay in tray; user clicks to open
  bootstrapCompleted: false, // set once after BootstrapRunner reports DONE
});

function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(fs.readFileSync(SETTINGS_FILE, "utf8")) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(patch) {
  const merged = { ...loadSettings(), ...patch };
  fs.mkdirSync(path.dirname(SETTINGS_FILE), { recursive: true });
  fs.writeFileSync(SETTINGS_FILE, JSON.stringify(merged, null, 2));
  return merged;
}

function syncAutoStart(enabled) {
  // Electron handles the registry key — same effect as a Windows Startup
  // shortcut but managed by the app so uninstall cleans it up.
  app.setLoginItemSettings({ openAtLogin: enabled, args: ["--hidden"] });
}

// ─── Single instance ──────────────────────────────────────────────────────

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  return; // noqa — second invocation tells the first to surface its window
}

// ─── Window + tray ────────────────────────────────────────────────────────

let mainWindow = null;
let tray = null;

function getOrCreateWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    return mainWindow;
  }
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: "OpenClaw",
    autoHideMenuBar: true,
    backgroundColor: "#0b0e14",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadURL(PANEL_URL);
  // Closing the X button hides instead of quits — app keeps running in tray.
  mainWindow.on("close", (event) => {
    if (!app._isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  // External links open in the default browser, not a new BrowserWindow.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(PANEL_URL)) return { action: "allow" };
    shell.openExternal(url);
    return { action: "deny" };
  });
  return mainWindow;
}

function _tunnelMenuItem() {
  switch (tunnel.state) {
    case TunnelState.RUNNING:
      return [
        {
          label: `URL từ xa: ${tunnel.url}`,
          click: () => {
            clipboard.writeText(tunnel.url);
            shell.openExternal(tunnel.url);
          },
        },
        {
          label: "  Copy URL",
          click: () => clipboard.writeText(tunnel.url),
        },
        {
          label: "  Tắt URL từ xa",
          click: () => tunnel.stop(),
        },
      ];
    case TunnelState.STARTING:
    case TunnelState.DOWNLOADING:
      return [{ label: "URL từ xa: đang khởi tạo…", enabled: false }];
    case TunnelState.ERROR:
      return [
        {
          label: "URL từ xa: lỗi — thử lại",
          click: () => tunnel.start().catch(() => rebuildTrayMenu()),
        },
      ];
    default:
      return [
        {
          label: "Bật URL từ xa (Cloudflare Tunnel)",
          click: () => tunnel.start().catch(() => rebuildTrayMenu()),
        },
      ];
  }
}

function buildTrayMenu() {
  const s = loadSettings();
  const platformLabel = process.platform === "win32" ? "Windows" : "máy";
  return Menu.buildFromTemplate([
    { label: "Mở Panel", click: () => getOrCreateWindow() },
    { type: "separator" },
    ..._tunnelMenuItem(),
    { type: "separator" },
    {
      label: `Khởi động cùng ${platformLabel}`,
      type: "checkbox",
      checked: s.autoStart,
      click: (item) => {
        saveSettings({ autoStart: item.checked });
        syncAutoStart(item.checked);
      },
    },
    {
      label: "Mở cửa sổ khi khởi động",
      type: "checkbox",
      checked: s.openWindowOnStart,
      click: (item) => saveSettings({ openWindowOnStart: item.checked }),
    },
    { type: "separator" },
    {
      label: "Thoát",
      click: () => {
        app._isQuitting = true;
        tunnel.stop().finally(() => app.quit());
      },
    },
  ]);
}

function rebuildTrayMenu() {
  if (tray) tray.setContextMenu(buildTrayMenu());
}

// React to tunnel lifecycle so the tray label flips live.
tunnel.on("state", rebuildTrayMenu);
tunnel.on("closed", rebuildTrayMenu);

function buildTray() {
  if (tray) return;
  const icon = fs.existsSync(TRAY_ICON) ? nativeImage.createFromPath(TRAY_ICON) : undefined;
  tray = new Tray(icon ?? nativeImage.createEmpty());
  tray.setToolTip("OpenClaw");
  tray.setContextMenu(buildTrayMenu());
  tray.on("click", () => getOrCreateWindow());
}

// ─── First-run wizard ─────────────────────────────────────────────────────

function openWizard() {
  const wizard = new BrowserWindow({
    width: 720,
    height: 520,
    title: "OpenClaw — Cài đặt lần đầu",
    resizable: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, "preload-wizard.js"),
    },
  });
  wizard.loadFile(path.join(__dirname, "../wizard/index.html"));
  return wizard;
}

async function runFirstRun() {
  const wizardWindow = openWizard();
  const runner = new BootstrapRunner({ app });

  // Stream every step + log line to the wizard renderer.
  runner.on("step", (e) => wizardWindow.webContents.send("bootstrap:step", e));
  runner.on("log", (e) => wizardWindow.webContents.send("bootstrap:log", e));

  try {
    const verdict = await runner.run();
    if (verdict === Step.DONE) {
      saveSettings({ bootstrapCompleted: true });
      wizardWindow.webContents.send("bootstrap:done");
    } else if (verdict === Step.REBOOT_REQUIRED) {
      wizardWindow.webContents.send("bootstrap:reboot");
    }
  } catch (err) {
    wizardWindow.webContents.send("bootstrap:error", { message: err.message });
  }
}

// ─── App lifecycle ────────────────────────────────────────────────────────

app.on("second-instance", () => getOrCreateWindow());

app.whenReady().then(async () => {
  buildTray();
  const settings = loadSettings();
  syncAutoStart(settings.autoStart);

  // First-run gate. If we've never finished bootstrap, force the wizard;
  // the tray stays accessible so the user can quit if they cancel.
  if (!settings.bootstrapCompleted) {
    await runFirstRun();
    return;
  }

  // Subsequent launches: optionally open the panel window. The
  // `--hidden` arg is set by login-item when Windows boots us so we
  // don't surface a window on every login.
  const launchedHidden = process.argv.includes("--hidden");
  if (settings.openWindowOnStart && !launchedHidden) {
    getOrCreateWindow();
  }
});

// macOS dev convenience — keep app alive without a window.
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    // Don't quit — tray keeps us alive on Windows.
  }
});

// ─── IPC ──────────────────────────────────────────────────────────────────

ipcMain.handle("settings:get", () => loadSettings());
ipcMain.handle("settings:set", (_e, patch) => {
  const next = saveSettings(patch);
  if ("autoStart" in patch) syncAutoStart(next.autoStart);
  rebuildTrayMenu();
  return next;
});
ipcMain.handle("wizard:retry", () => runFirstRun());
ipcMain.handle("tunnel:start", () => tunnel.start());
ipcMain.handle("tunnel:stop", () => tunnel.stop());
ipcMain.handle("tunnel:status", () => ({ state: tunnel.state, url: tunnel.url }));
