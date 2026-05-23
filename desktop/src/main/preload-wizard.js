// Preload bridge for the first-run wizard.
//
// Renderer (sandboxed) listens for IPC events fired by bootstrap-runner
// and exposes a minimal control surface back to main.

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("openclawWizard", {
  platform: process.platform, // "linux" | "win32" | "darwin"
  onStep: (cb) => ipcRenderer.on("bootstrap:step", (_e, payload) => cb(payload)),
  onLog: (cb) => ipcRenderer.on("bootstrap:log", (_e, payload) => cb(payload)),
  onDone: (cb) => ipcRenderer.on("bootstrap:done", () => cb()),
  onReboot: (cb) => ipcRenderer.on("bootstrap:reboot", () => cb()),
  onError: (cb) => ipcRenderer.on("bootstrap:error", (_e, payload) => cb(payload)),
  onPreflight: (cb) => ipcRenderer.on("bootstrap:preflight", (_e, payload) => cb(payload)),
  retry: () => ipcRenderer.invoke("wizard:retry"),
  openTerminal: () => ipcRenderer.invoke("wizard:open-terminal"),
});
