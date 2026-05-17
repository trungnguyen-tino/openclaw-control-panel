#!/usr/bin/env bash
# Build a release tarball for openclaw-panel.
#
# Output: dist/openclaw-panel-<TAG>.tar.gz + dist/openclaw-panel-<TAG>.tar.gz.sha256
# Usage : scripts/build-release-tarball.sh <TAG>
#   TAG defaults to `git describe --tags --always` or `latest`.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  TAG=$(git describe --tags --always 2>/dev/null || echo "latest")
fi

DIST="$ROOT/dist"
STAGE="$DIST/_stage"
NAME="openclaw-panel-${TAG}"
TARBALL="$DIST/${NAME}.tar.gz"

rm -rf "$DIST"
mkdir -p "$STAGE/$NAME"

echo "[build] Building UI"
if [[ -d ui ]]; then
  ( cd ui && npm ci && npm run build )
fi

echo "[build] Staging artifacts"
cp -r app "$STAGE/$NAME/"
cp -r systemd "$STAGE/$NAME/"
cp -r scripts "$STAGE/$NAME/" 2>/dev/null || true
[[ -d static/dist ]] && cp -r static "$STAGE/$NAME/"
cp requirements.txt wsgi.py "$STAGE/$NAME/"
cp install.sh "$STAGE/$NAME/" 2>/dev/null || true
[[ -f README.md ]] && cp README.md "$STAGE/$NAME/"

echo "[build] Cleaning bytecode + caches"
find "$STAGE/$NAME" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "[build] Creating tarball"
( cd "$STAGE" && tar -czf "$TARBALL" "$NAME" )
sha256sum "$TARBALL" | awk '{print $1}' > "${TARBALL}.sha256"
rm -rf "$STAGE"

echo "[build] Done:"
echo "  $TARBALL"
echo "  $(cat "${TARBALL}.sha256")  ${NAME}.tar.gz"
