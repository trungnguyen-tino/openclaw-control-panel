#!/usr/bin/env bash
# build-offline-bundle.sh — Tạo offline installer zip.
#
# Output: dist/openclaw-panel-offline-<VERSION>.zip
#
# User chỉ cần:
#   unzip openclaw-panel-offline-X.Y.Z.zip
#   cd openclaw-panel-offline-X.Y.Z
#   sudo bash install-local.sh --domain X --no-firewall --skip-chrome
#
# Không cần GitHub, không cần internet (trừ apt + npm install lúc setup VPS).

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$(git describe --tags --always 2>/dev/null || echo "latest")
fi

DIST="$ROOT/dist"
BUNDLE_NAME="openclaw-panel-offline-${VERSION}"
ZIP="$DIST/${BUNDLE_NAME}.zip"

# Build the panel tarball FIRST (build-release-tarball.sh wipes $DIST).
echo "[bundle] Building tarball..."
bash scripts/build-release-tarball.sh "$VERSION" >/dev/null

# Now create bundle dir under $DIST (after tarball lives there).
BUNDLE_DIR="$DIST/$BUNDLE_NAME"
rm -rf "$BUNDLE_DIR" "$ZIP"
mkdir -p "$BUNDLE_DIR"

# Copy artifacts into bundle directory.
echo "[bundle] Copying artifacts..."
cp "$DIST/openclaw-panel-${VERSION}.tar.gz" "$BUNDLE_DIR/openclaw-panel.tar.gz"
cp "$DIST/openclaw-panel-${VERSION}.tar.gz.sha256" "$BUNDLE_DIR/openclaw-panel.tar.gz.sha256"
cp install.sh "$BUNDLE_DIR/"

# Inline wrapper that the user invokes.
cat > "$BUNDLE_DIR/install-local.sh" <<'WRAPPER'
#!/usr/bin/env bash
# install-local.sh — Offline OpenClaw Panel installer wrapper.
#
# Usage:
#   sudo bash install-local.sh --domain openclaw.example.com [extra install.sh flags]
#
# Forwards all flags to install.sh after auto-pointing --tarball at the local tarball.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TARBALL="$HERE/openclaw-panel.tar.gz"

if [[ ! -f "$TARBALL" ]]; then
  echo "[err] Tarball missing: $TARBALL" >&2
  echo "[err] Did you unzip the bundle correctly?" >&2
  exit 1
fi

exec bash "$HERE/install.sh" --tarball "$TARBALL" "$@"
WRAPPER

cat > "$BUNDLE_DIR/README.txt" <<README
OpenClaw Panel — Offline Installer Bundle
=========================================

Version: ${VERSION}
Contents:
  install-local.sh           ← entrypoint (call this)
  install.sh                 ← main installer (auto-invoked)
  openclaw-panel.tar.gz      ← panel code + SPA
  openclaw-panel.tar.gz.sha256

Tested on: Ubuntu 22.04 + 24.04 (x86_64)

Quick install:
--------------
  sudo bash install-local.sh \\
    --domain openclaw.example.com \\
    --no-firewall \\
    --skip-chrome

Domain options:
  - Public FQDN: openclaw.example.com (auto Let's Encrypt cert)
  - LAN IP: 192.168.1.50           (Caddy tls internal, self-signed)
  - http://IP                       (no SSL)

Flags (all forwarded to install.sh):
  --domain <DOMAIN>          (REQUIRED)
  --mgmt-key <KEY>           (optional) supply MGMT API key, default auto-generated
  --no-firewall              (optional) skip ufw setup
  --skip-chrome              (optional) skip Google Chrome (~600MB saved)
  --force                    (optional) suppress legacy detected warning

The installer needs internet ONLY for apt + npm + Caddy package downloads
(~200MB on fresh Ubuntu). No GitHub access required.

Post-install:
  - Panel: https://<DOMAIN>/
  - MGMT API key: printed at end + saved to /opt/openclaw/.env
  - Gateway Control: https://<DOMAIN>/gw/#token=<GATEWAY_TOKEN>
README

# sha256 of the bundle itself (defense against tampering during transport).
echo "[bundle] Computing bundle sha256..."
( cd "$BUNDLE_DIR" && find . -type f ! -name '*.sha256' -exec sha256sum {} + > MANIFEST.sha256 )

# Zip it.
echo "[bundle] Zipping..."
( cd "$DIST" && zip -qr "${BUNDLE_NAME}.zip" "$BUNDLE_NAME" )

# Outer sha256 of the zip.
( cd "$DIST" && sha256sum "${BUNDLE_NAME}.zip" | awk '{print $1}' > "${BUNDLE_NAME}.zip.sha256" )

echo
echo "[bundle] Done:"
echo "  $ZIP"
echo "  $(cat "${ZIP}.sha256")  ${BUNDLE_NAME}.zip"
echo
echo "Transfer to target VPS via any method (scp, sftp, USB, etc):"
echo "  scp $ZIP root@<VPS-IP>:/tmp/"
echo "  ssh root@<VPS-IP>"
echo "  cd /tmp && unzip ${BUNDLE_NAME}.zip && cd ${BUNDLE_NAME}"
echo "  sudo bash install-local.sh --domain openclaw.example.com --no-firewall"
