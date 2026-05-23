// WSL2 + Ubuntu distro detection.
//
// Architecture B routes all backend work through a WSL2 Ubuntu distro, so
// this module is the gatekeeper for first-run setup: it inspects the host,
// decides what (if anything) needs to be installed, and returns a verdict
// the renderer wizard can act on.

"use strict";

const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

const execFileAsync = promisify(execFile);

const REQUIRED_DISTRO = "Ubuntu-22.04";

// Possible verdicts from probe(). Renderer maps these to wizard screens.
const Status = Object.freeze({
  READY: "ready", // WSL2 present + required distro installed
  WSL_MISSING: "wsl_missing", // `wsl.exe` not on PATH
  WSL_LEGACY: "wsl_legacy", // WSL1 only — needs `wsl --set-default-version 2`
  DISTRO_MISSING: "distro_missing", // WSL2 OK but Ubuntu-22.04 not installed
  ERROR: "error", // probe failed unexpectedly
});

async function _runWsl(args, timeoutMs = 8000) {
  // wsl.exe emits UTF-16LE by default; the `WSL_UTF8=1` env switch makes
  // it use UTF-8 so we can parse output without surrogate-pair hassles.
  const { stdout, stderr } = await execFileAsync("wsl.exe", args, {
    timeout: timeoutMs,
    windowsHide: true,
    env: { ...process.env, WSL_UTF8: "1" },
  });
  return { stdout: stdout.toString("utf8"), stderr: stderr.toString("utf8") };
}

async function probe() {
  if (process.platform !== "win32") {
    return { status: Status.ERROR, reason: "wsl-detector only runs on win32" };
  }
  // 1. Is wsl.exe even callable?
  try {
    await execFileAsync("wsl.exe", ["--status"], { timeout: 5000, windowsHide: true });
  } catch (err) {
    if (err.code === "ENOENT") return { status: Status.WSL_MISSING };
    return { status: Status.ERROR, reason: `wsl --status failed: ${err.message}` };
  }
  // 2. Is the default version 2? (`wsl --status` exposes "Default Version: 2")
  let statusOut;
  try {
    statusOut = (await _runWsl(["--status"])).stdout;
  } catch (err) {
    return { status: Status.ERROR, reason: `wsl --status read failed: ${err.message}` };
  }
  if (!/Default Version:\s*2/i.test(statusOut)) {
    return { status: Status.WSL_LEGACY, statusOut };
  }
  // 3. Does the required distro exist? `wsl -l -q` prints distro names, one per line.
  let listOut;
  try {
    listOut = (await _runWsl(["-l", "-q"])).stdout;
  } catch (err) {
    return { status: Status.ERROR, reason: `wsl -l -q failed: ${err.message}` };
  }
  const distros = listOut
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!distros.includes(REQUIRED_DISTRO)) {
    return { status: Status.DISTRO_MISSING, distros };
  }
  return { status: Status.READY, distros };
}

// Convenience: forwards a shell command into the required distro as root.
// Used by bootstrap-runner to invoke install.sh / bootstrap-fix.sh.
async function execInDistro(commandLine, { timeoutMs = 600_000 } = {}) {
  return _runWsl(["-d", REQUIRED_DISTRO, "-u", "root", "--", "bash", "-lc", commandLine], timeoutMs);
}

module.exports = { Status, REQUIRED_DISTRO, probe, execInDistro };

// Allow `node wsl-detector.js` as a smoke test from a Windows shell.
if (require.main === module) {
  probe().then((r) => {
    console.log(JSON.stringify(r, null, 2));
    process.exit(r.status === Status.READY ? 0 : 1);
  });
}
