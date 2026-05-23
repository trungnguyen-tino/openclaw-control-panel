// First-run orchestrator: take the host from "nothing installed" to
// "openclaw-mgmt is serving 127.0.0.1:9998" with progress events that the
// wizard UI streams to the user.
//
// Strategy:
//   1. wsl-detector.probe()         → see what we already have
//   2. install WSL2 if missing      → `wsl --install --no-distribution`
//   3. install Ubuntu-22.04 distro  → `wsl --install -d Ubuntu-22.04`
//   4. run bootstrap-fix.sh         → exec inside the distro as root
//
// Steps 2 + 3 each need a reboot on most fresh Windows images — the
// wizard surfaces that to the user instead of swallowing it silently.

"use strict";

const { execFile, spawn } = require("node:child_process");
const { promisify } = require("node:util");
const { EventEmitter } = require("node:events");

const wsl = require("./wsl-detector");

const execFileAsync = promisify(execFile);

const Step = Object.freeze({
  PROBE: "probe",
  INSTALL_WSL: "install_wsl",
  REBOOT_REQUIRED: "reboot_required",
  INSTALL_DISTRO: "install_distro",
  PROVISION_DISTRO: "provision_distro", // first-run "set unix user" prompt
  RUN_BOOTSTRAP: "run_bootstrap",
  HEALTHCHECK: "healthcheck",
  DONE: "done",
  FAILED: "failed",
});

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

  // Promise that resolves to the final Step value, or rejects with Error.
  async run() {
    this._step(Step.PROBE);
    const probe = await wsl.probe();

    if (probe.status === wsl.Status.WSL_MISSING) {
      this._step(Step.INSTALL_WSL);
      await this._installWsl();
      // `wsl --install` requires a reboot before the distro can start. The
      // wizard tells the user to reboot and re-launch the app.
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

    // Distro is now present and the root user is usable.
    this._step(Step.RUN_BOOTSTRAP);
    await this._runBootstrap();

    this._step(Step.HEALTHCHECK);
    await this._healthcheck();

    this._step(Step.DONE);
    return Step.DONE;
  }

  async _installWsl() {
    // `--no-distribution` keeps the install fast and unattended; we install
    // Ubuntu in a separate step so we can report progress for each.
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

  // Fresh Ubuntu image's first launch normally prompts for a non-root unix
  // user — we don't want that interactive flow. Force root-only mode so
  // every subsequent `wsl -d Ubuntu-22.04 -u root` works without UID 1000.
  async _provisionDistroRoot() {
    await wsl.execInDistro("echo '[boot]\\ndefault=root' > /etc/wsl.conf");
  }

  async _runBootstrap() {
    // Fresh WSL2 distro has nothing installed — call bootstrap.sh which
    // wraps install.sh to apt-install node + python + caddy, npm-install
    // openclaw@latest, extract the panel tarball, and bring up the three
    // systemd units. `bootstrap-fix.sh` is *upgrade-only* (assumes panel
    // already installed) so it would skip every prerequisite here.
    //
    // Domain = 127.0.0.1 keeps Caddy on self-signed `tls internal` mode;
    // Electron talks directly to gunicorn :9998 so Caddy is mostly
    // dormant in this deployment.
    const installArgs = "--domain 127.0.0.1";
    // Stream stdout/stderr line-by-line so the wizard sees real-time
    // progress through ~5-10 min of apt-get + npm install.
    await new Promise((resolve, reject) => {
      const child = spawn(
        "wsl.exe",
        [
          "-d",
          wsl.REQUIRED_DISTRO,
          "-u",
          "root",
          "--",
          "bash",
          "-lc",
          `curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap.sh | bash -s -- ${installArgs}`,
        ],
        { windowsHide: true }
      );
      let stderr = "";
      child.stderr.on("data", (d) => {
        const text = d.toString("utf8");
        stderr += text;
        this.emit("log", { stream: "stderr", text });
      });
      child.stdout.on("data", (d) =>
        this.emit("log", { stream: "stdout", text: d.toString("utf8") })
      );
      child.on("error", reject);
      child.on("close", (code) =>
        code === 0
          ? resolve()
          : reject(new Error(`bootstrap exited ${code}: ${stderr.slice(0, 4000)}`))
      );
    });
  }

  async _healthcheck() {
    // localhost in WSL2 transparently forwards to Windows. Probe through
    // the distro so we don't depend on Windows networking quirks during
    // first boot (Defender Firewall prompts, etc).
    const r = await wsl.execInDistro(
      "curl -sSf -o /dev/null -w '%{http_code}' http://127.0.0.1:9998/api/health"
    );
    if (!/^200$/.test(r.stdout.trim())) {
      this._fail(`mgmt-api healthcheck returned ${r.stdout.trim() || "<empty>"}`);
    }
  }
}

module.exports = { BootstrapRunner, Step };
