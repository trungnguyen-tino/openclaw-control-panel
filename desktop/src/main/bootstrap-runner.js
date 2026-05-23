// First-run orchestrator — takes the host from "nothing installed" to
// "openclaw-mgmt is serving 127.0.0.1:9998", with progress events the
// wizard streams to the user.
//
// Two platform branches, picked at runtime:
//
//   Linux  → pkexec bash -c 'curl bootstrap.sh | bash -s -- --domain 127.0.0.1'
//            (polkit GUI password prompt; backend runs on the host directly,
//            no WSL involved).
//
//   Win32  → install WSL2 + Ubuntu-22.04 distro if missing, then run
//            bootstrap.sh INSIDE the distro via `wsl -- bash -lc '…'`.
//
// Both branches short-circuit if the backend is already healthy on
// localhost:9998 — handy when the user manually pre-installed via
// `curl … | sudo bash`, or when they launch the app after a successful
// bootstrap.

"use strict";

const { execFile, spawn } = require("node:child_process");
const { promisify } = require("node:util");
const { EventEmitter } = require("node:events");
const http = require("node:http");

const wsl = require("./wsl-detector");

const execFileAsync = promisify(execFile);

const BOOTSTRAP_URL =
  "https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh";
const PANEL_PORT = 9998;

const Step = Object.freeze({
  PROBE: "probe",
  PREFLIGHT: "preflight",
  INSTALL_WSL: "install_wsl",
  REBOOT_REQUIRED: "reboot_required",
  INSTALL_DISTRO: "install_distro",
  PROVISION_DISTRO: "provision_distro",
  RUN_BOOTSTRAP: "run_bootstrap",
  HEALTHCHECK: "healthcheck",
  DONE: "done",
  FAILED: "failed",
});

// Binaries required on the Linux path before we can run bootstrap.sh.
// `pkexec` (from policykit-1) opens the GUI sudo prompt; `curl` fetches
// the bootstrap script; `bash` runs it. Almost always pre-installed on
// Ubuntu Desktop, but minimal/server images may be missing some.
const LINUX_PREREQS = Object.freeze([
  { bin: "pkexec", pkg: "policykit-1" },
  { bin: "curl", pkg: "curl" },
  { bin: "bash", pkg: "bash" },
]);

async function _whichLinux(bin) {
  try {
    await execFileAsync("/usr/bin/which", [bin], { timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}

function _httpHealthcheck(port = PANEL_PORT, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: "/api/health", timeout: timeoutMs },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

class BootstrapRunner extends EventEmitter {
  constructor({ app } = {}) {
    super();
    this._app = app;
    this._cancelled = false;
  }

  cancel() {
    this._cancelled = true;
    this.emit("cancelled");
  }

  _step(step, extra = {}) {
    this.emit("step", { step, ...extra });
  }

  _fail(reason, extra = {}) {
    this._step(Step.FAILED, { reason, ...extra });
    throw new Error(reason);
  }

  async run() {
    // Already healthy? (Manual pre-install, or re-launch after a previous
    // successful bootstrap.) Skip the whole flow.
    this._step(Step.PROBE);
    if (await _httpHealthcheck()) {
      this._step(Step.DONE);
      return Step.DONE;
    }

    if (process.platform === "linux") {
      return this._runLinux();
    }
    if (process.platform === "win32") {
      return this._runWindows();
    }
    this._fail(`Unsupported platform: ${process.platform}`);
  }

  // ─── Linux (Ubuntu Desktop) ──────────────────────────────────────────

  async _runLinux() {
    this._step(Step.PREFLIGHT);
    const missing = [];
    for (const { bin, pkg } of LINUX_PREREQS) {
      if (!(await _whichLinux(bin))) missing.push({ bin, pkg });
    }
    if (missing.length) {
      const pkgs = [...new Set(missing.map((m) => m.pkg))].join(" ");
      const cmd = `sudo apt update && sudo apt install -y ${pkgs}`;
      this.emit("preflight", {
        missing,
        installCommand: cmd,
        hint:
          `Thiếu công cụ: ${missing.map((m) => m.bin).join(", ")}. ` +
          "Mở Terminal, chạy lệnh dưới, rồi quay lại bấm 'Đã chạy xong'.",
      });
      this._fail("preflight: missing required binaries");
    }

    this._step(Step.RUN_BOOTSTRAP);
    // `pkexec` opens the desktop's polkit password dialog so the user
    // grants sudo with a GUI prompt — required for apt-install + systemd
    // unit writes. `bash -c '…'` is run as root after auth succeeds.
    const cmd = `curl -fsSL ${BOOTSTRAP_URL} | bash -s -- --domain 127.0.0.1`;
    await this._spawnStreaming("pkexec", ["bash", "-c", cmd]);

    this._step(Step.HEALTHCHECK);
    if (!(await _httpHealthcheck(PANEL_PORT, 10_000))) {
      this._fail("Linux bootstrap finished but :9998 still unreachable");
    }
    this._step(Step.DONE);
    return Step.DONE;
  }

  // ─── Windows (WSL2 + Ubuntu-22.04 distro) ────────────────────────────

  async _runWindows() {
    const probe = await wsl.probe();

    if (probe.status === wsl.Status.WSL_MISSING) {
      this._step(Step.INSTALL_WSL);
      await this._installWsl();
      this._step(Step.REBOOT_REQUIRED);
      return Step.REBOOT_REQUIRED;
    }
    if (probe.status === wsl.Status.WSL_LEGACY) {
      this._fail(
        "WSL is installed but defaulted to v1. Open an Admin shell and run:\n" +
          "  wsl --set-default-version 2\n" +
          "then restart this app."
      );
    }
    if (probe.status === wsl.Status.ERROR) {
      this._fail(probe.reason || "WSL probe failed");
    }
    if (probe.status === wsl.Status.DISTRO_MISSING) {
      this._step(Step.INSTALL_DISTRO);
      await this._installDistro();
      this._step(Step.PROVISION_DISTRO);
      await this._provisionDistroRoot();
    }

    this._step(Step.RUN_BOOTSTRAP);
    await this._spawnStreaming("wsl.exe", [
      "-d",
      wsl.REQUIRED_DISTRO,
      "-u",
      "root",
      "--",
      "bash",
      "-lc",
      `curl -fsSL ${BOOTSTRAP_URL} | bash -s -- --domain 127.0.0.1`,
    ]);

    this._step(Step.HEALTHCHECK);
    // Probe through the distro — localhost forwarding is sometimes slow
    // to attach the first time, and probing from Windows-side can race.
    const r = await wsl.execInDistro(
      `curl -sSf -o /dev/null -w '%{http_code}' http://127.0.0.1:${PANEL_PORT}/api/health`
    );
    if (!/^200$/.test(r.stdout.trim())) {
      this._fail(`mgmt-api healthcheck returned ${r.stdout.trim() || "<empty>"}`);
    }
    this._step(Step.DONE);
    return Step.DONE;
  }

  async _installWsl() {
    await execFileAsync(
      "wsl.exe",
      ["--install", "--no-distribution", "--no-launch"],
      { timeout: 600_000, windowsHide: true }
    );
  }

  async _installDistro() {
    await execFileAsync(
      "wsl.exe",
      ["--install", "-d", wsl.REQUIRED_DISTRO, "--no-launch"],
      { timeout: 900_000, windowsHide: true }
    );
  }

  async _provisionDistroRoot() {
    await wsl.execInDistro("echo '[boot]\\ndefault=root' > /etc/wsl.conf");
  }

  // ─── Shared helpers ──────────────────────────────────────────────────

  // Spawns a child + forwards stdout/stderr as `log` events. Resolves on
  // exit code 0; rejects with an Error carrying tail of stderr otherwise.
  _spawnStreaming(file, args, { timeoutMs = 1_200_000 } = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(file, args, { windowsHide: true });
      let stderr = "";
      const timer = setTimeout(() => {
        child.kill("SIGTERM");
        reject(new Error(`${file} timed out after ${Math.round(timeoutMs / 1000)}s`));
      }, timeoutMs);
      child.stdout.on("data", (d) =>
        this.emit("log", { stream: "stdout", text: d.toString("utf8") })
      );
      child.stderr.on("data", (d) => {
        const text = d.toString("utf8");
        stderr += text;
        this.emit("log", { stream: "stderr", text });
      });
      child.on("error", (err) => {
        clearTimeout(timer);
        reject(err);
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        if (code === 0) return resolve();
        reject(new Error(`${file} exited ${code}: ${stderr.slice(-4000)}`));
      });
    });
  }
}

module.exports = { BootstrapRunner, Step, PANEL_PORT };
