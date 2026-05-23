// Cloudflare Quick Tunnel manager — exposes the local panel at a
// throwaway `https://<random>.trycloudflare.com` URL with zero
// configuration (no Cloudflare account, no DNS, no certificates).
//
// Lifecycle:
//   start() → download cloudflared if missing → spawn the tunnel
//             child process → parse stdout for the public URL →
//             emit "url" event when ready.
//   stop()  → SIGTERM the child + wait for graceful shutdown.
//
// Privacy posture: never auto-starts. The user must explicitly click
// "URL từ xa" in the tray; the tunnel stops when the app quits or the
// user toggles it off.

"use strict";

const { spawn } = require("node:child_process");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const path = require("node:path");
const https = require("node:https");
const os = require("node:os");

const LOCAL_PORT = 9998;

// Pre-built binaries from Cloudflare's release bucket — keep this map
// pinned so we don't break on upstream URL changes.
const RELEASES = Object.freeze({
  "linux-x64":
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
  "linux-arm64":
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64",
  "win32-x64":
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
});

const State = Object.freeze({
  IDLE: "idle",
  DOWNLOADING: "downloading",
  STARTING: "starting",
  RUNNING: "running",
  STOPPING: "stopping",
  ERROR: "error",
});

function _platformKey() {
  const arch = process.arch === "arm64" ? "arm64" : "x64";
  return `${process.platform}-${arch}`;
}

function _binaryPath(app) {
  const root = app ? app.getPath("userData") : path.join(os.tmpdir(), "openclaw-cf");
  const exe = process.platform === "win32" ? "cloudflared.exe" : "cloudflared";
  return path.join(root, "bin", exe);
}

async function _ensureDir(p) {
  await fsp.mkdir(path.dirname(p), { recursive: true });
}

function _download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest, { mode: 0o755 });
    function get(u) {
      https
        .get(u, (res) => {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            res.resume();
            get(res.headers.location);
            return;
          }
          if (res.statusCode !== 200) {
            file.destroy();
            reject(new Error(`download ${u} → HTTP ${res.statusCode}`));
            return;
          }
          res.pipe(file);
          file.on("finish", () => file.close(resolve));
        })
        .on("error", reject);
    }
    get(url);
  });
}

class CloudflaredManager extends EventEmitter {
  constructor({ app } = {}) {
    super();
    this._app = app;
    this._state = State.IDLE;
    this._child = null;
    this._url = null;
  }

  get state() {
    return this._state;
  }
  get url() {
    return this._url;
  }

  _setState(next, extra = {}) {
    this._state = next;
    this.emit("state", { state: next, ...extra });
  }

  async ensureBinary() {
    const dest = _binaryPath(this._app);
    if (fs.existsSync(dest)) return dest;
    const key = _platformKey();
    const url = RELEASES[key];
    if (!url) throw new Error(`No cloudflared release for ${key}`);
    this._setState(State.DOWNLOADING, { url });
    await _ensureDir(dest);
    await _download(url, dest);
    if (process.platform !== "win32") await fsp.chmod(dest, 0o755);
    return dest;
  }

  async start() {
    if (this._state === State.RUNNING || this._state === State.STARTING) return this._url;
    try {
      const bin = await this.ensureBinary();
      this._setState(State.STARTING);
      this._url = null;
      this._child = spawn(
        bin,
        [
          "tunnel",
          "--no-autoupdate",
          "--url",
          `http://127.0.0.1:${LOCAL_PORT}`,
        ],
        { windowsHide: true }
      );
      // cloudflared logs to stderr by default. Each line is JSON-ish but
      // free-form; we grep for the trycloudflare URL on first appearance.
      const urlRe = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i;
      const onChunk = (buf) => {
        const text = buf.toString("utf8");
        this.emit("log", text);
        if (!this._url) {
          const m = text.match(urlRe);
          if (m) {
            this._url = m[0];
            this._setState(State.RUNNING, { url: m[0] });
            this.emit("url", m[0]);
          }
        }
      };
      this._child.stdout.on("data", onChunk);
      this._child.stderr.on("data", onChunk);
      this._child.on("close", (code) => {
        const wasRunning = this._state === State.RUNNING;
        this._child = null;
        this._url = null;
        if (this._state !== State.STOPPING) {
          this._setState(State.ERROR, { code });
        } else {
          this._setState(State.IDLE);
        }
        this.emit("closed", { code, wasRunning });
      });
      return new Promise((resolve, reject) => {
        // Resolve once we either get a URL (success) or the process dies
        // without producing one (failure). 30s upper bound — first hop
        // through Cloudflare's edge usually completes in <5s.
        const timer = setTimeout(() => {
          reject(new Error("cloudflared did not emit a URL within 30s"));
          this.stop();
        }, 30_000);
        this.once("url", (u) => {
          clearTimeout(timer);
          resolve(u);
        });
        this.once("closed", () => {
          clearTimeout(timer);
          if (!this._url) reject(new Error("cloudflared exited before emitting URL"));
        });
      });
    } catch (err) {
      this._setState(State.ERROR, { reason: err.message });
      throw err;
    }
  }

  async stop() {
    if (!this._child) {
      this._setState(State.IDLE);
      return;
    }
    this._setState(State.STOPPING);
    const child = this._child;
    return new Promise((resolve) => {
      child.once("close", () => resolve());
      child.kill("SIGTERM");
      // Hard kill after 5s if it didn't honour SIGTERM.
      setTimeout(() => {
        if (this._child === child) child.kill("SIGKILL");
      }, 5000);
    });
  }
}

module.exports = { CloudflaredManager, State, LOCAL_PORT };
