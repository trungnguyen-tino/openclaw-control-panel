#!/usr/bin/env bash
# Universal in-place upgrade for openclaw-panel.
#
# Bypasses the broken self-update path (≤ v0.2.9 _swap never promoted
# current/ → live) by downloading the release tarball and copying it
# directly on top of /opt/openclaw-mgmt/. Idempotent and version-agnostic.
#
# Usage:
#   curl -fsSL https://github.com/trungnguyen-tino/openclaw-control-panel/releases/download/v0.2.10/bootstrap-fix.sh \
#     | sudo bash
#
#   # Or pin a different version:
#   curl -fsSL .../bootstrap-fix.sh | sudo TAG=v0.2.10 bash

set -euo pipefail

TAG="${TAG:-v0.2.10}"
REPO="${REPO:-trungnguyen-tino/openclaw-control-panel}"
URL="https://github.com/${REPO}/releases/download/${TAG}/openclaw-panel.tar.gz"

MGMT_DIR=/opt/openclaw-mgmt
ENV_FILE=/opt/openclaw/.env

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

if [[ ! -d "$MGMT_DIR" ]]; then
  echo "ERROR: $MGMT_DIR not found — is openclaw-panel installed?" >&2
  exit 1
fi

echo "[bootstrap-fix] tag=$TAG repo=$REPO"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

echo "[1/5] Download tarball"
curl -fsSL "$URL" -o panel.tar.gz
tar -xzf panel.tar.gz
SRC=$(find . -maxdepth 1 -type d -name "openclaw-panel" -print -quit)
[[ -d "$SRC" ]] || { echo "ERROR: tarball layout unexpected" >&2; exit 1; }

echo "[2/5] Promote code → live position ($MGMT_DIR)"
cp -arT "$SRC/" "$MGMT_DIR/"

echo "[3/5] Install helper scripts → /usr/local/bin"
for s in openclaw-healthcheck.sh openclaw-sync-auth-profiles.sh openclaw-config-enforce.sh; do
  if [[ -f "$SRC/scripts/$s" ]]; then
    install -m 755 "$SRC/scripts/$s" /usr/local/bin/
  fi
done

echo "[4/5] Switch release URL → public repo (if pointing at private)"
if [[ -f "$ENV_FILE" ]] && grep -q "/openclaw-panel/releases" "$ENV_FILE"; then
  sed -i 's|/openclaw-panel/releases|/openclaw-control-panel/releases|g' "$ENV_FILE"
  echo "       env updated"
else
  echo "       env already points at public (or .env missing — skipped)"
fi

echo "[5/5] Schedule openclaw-mgmt restart in 10s"
systemctl daemon-reload
# When this script runs from the panel's own Terminal page, the moment
# openclaw-mgmt restarts the SSE session dies and bash receives SIGTERM
# before the verify block can print. `systemctl --no-block` was still
# racy because systemd kicks the restart job almost immediately.
#
# Use systemd-run --on-active=10 to push the restart 10 seconds into
# the future. systemd-run exits in milliseconds (no race), then the
# verify block below runs to completion within the 10s window, then
# systemd fires the restart cleanly.
systemd-run --on-active=10 --quiet --unit=openclaw-mgmt-bootstrap-restart \
  /usr/bin/systemctl restart openclaw-mgmt 2>/dev/null || \
  systemctl --no-block restart openclaw-mgmt   # fallback if systemd-run unavailable

# ---- verify (runs BEFORE the scheduled restart fires) ----
echo
if grep -q "_promote_to_live" "$MGMT_DIR/app/services/self_update_service.py" 2>/dev/null; then
  echo "[verify] code: $TAG đã cài (promote-to-live present)"
else
  echo "[verify] WARNING: _promote_to_live marker missing — tarball older than v0.2.10?" >&2
fi

if systemctl is-active --quiet openclaw-mgmt; then
  echo "[verify] openclaw-mgmt: active (sẽ tự restart sau ~10s để load code mới)"
else
  echo "[verify] WARNING: openclaw-mgmt KHÔNG active — chạy: journalctl -u openclaw-mgmt -n 50" >&2
fi

if curl -sSf -o /dev/null -w "[verify] http://127.0.0.1:9998/api/health → %{http_code}\n" \
    http://127.0.0.1:9998/api/health; then
  :
else
  echo "[verify] WARNING: api/health unreachable on localhost" >&2
fi

echo
echo "Done. openclaw-mgmt sẽ tự restart trong ~10 giây để load code $TAG."
echo "Sau khi restart, Terminal page sẽ reconnect tự động."
echo "Future panel self-updates with tag=latest will work end-to-end."
