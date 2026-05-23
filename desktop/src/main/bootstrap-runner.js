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
const path = require("node:path");
const fs = require("node:fs");

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

// Path to the bundled bootstrap-fix.sh — resolved differently in dev (relative
// to repo) vs packaged (resources/ inside the installed app).
function _bootstrapScriptPath(app) {
  if (app && app.isPackaged) {
    return path.join(process.resourcesPath, "bootstrap-fix.sh");
  }
  return path.resolve(__dirname, "../../../scripts/bootstrap-fix.sh");
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
    // Bootstrap script is shipped as a release asset; we ALSO bundle a
    // copy inside the installer in case the host has no Internet on
    // first run. Prefer the local copy when present.
    const local = _bootstrapScriptPath(this._app);
    if (fs.existsSync(local)) {
      // Stream the local script into the distro's stdin so we don't need
      // a Windows→Linux path translation. Distro reads from stdin and pipes
      // it into `bash`.
      await new Promise((resolve, reject) => {
        const child = spawn(
          "wsl.exe",
          ["-d", wsl.REQUIRED_DISTRO, "-u", "root", "--", "bash", "-s"],
          { windowsHide: true }
        );
        const script = fs.createReadStream(local);
        script.pipe(child.stdin);
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
      return;
    }
    // Fallback: fetch the public release asset over the wire from inside
    // the distro itself (faster + simpler than going through Windows).
    await wsl.execInDistro(
      "curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/latest/download/bootstrap-fix.sh | bash"
    );
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
