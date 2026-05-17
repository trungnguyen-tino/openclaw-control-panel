#!/usr/bin/env bash
# Publish OpenClaw Panel as a GitHub Release.
#
# What it does:
# 1. Build SPA + create release tarball under dist/
# 2. Create (or update) GitHub Release for <TAG>
# 3. Upload `install.sh` + `openclaw-panel.tar.gz` + sha256 as release assets
#
# Usage:
#   scripts/publish-github-release.sh v0.1.0
#   scripts/publish-github-release.sh v0.2.0 --notes "bug fixes"
#
# Requires: gh CLI authenticated, current dir = repo root.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

TAG="${1:-}"
shift || true
NOTES="${1:-Auto-generated release}"

if [[ -z "$TAG" ]]; then
  echo "usage: $0 <tag> [release-notes]" >&2
  exit 1
fi

# Repo owner/name resolved from gh CLI to keep one-liner URL correct.
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "[release] Repo: $REPO  Tag: $TAG"

# Build release tarball — name without version so /latest/download URL is stable.
DIST="$ROOT/dist"
STAGE="$DIST/_stage"
NAME="openclaw-panel"
TARBALL="$DIST/${NAME}.tar.gz"

rm -rf "$DIST"
mkdir -p "$STAGE/$NAME"

echo "[release] Building UI"
( cd ui && npm ci --silent && npm run build )

echo "[release] Staging artifacts"
cp -r app systemd "$STAGE/$NAME/"
[[ -d scripts ]] && cp -r scripts "$STAGE/$NAME/"
[[ -d static/dist ]] && cp -r static "$STAGE/$NAME/"
cp requirements.txt wsgi.py "$STAGE/$NAME/"
cp install.sh "$STAGE/$NAME/"
[[ -f README.md ]] && cp README.md "$STAGE/$NAME/"

echo "[release] Cleaning bytecode + caches"
find "$STAGE/$NAME" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "[release] Creating tarball"
( cd "$STAGE" && tar -czf "$TARBALL" "$NAME" )
sha256sum "$TARBALL" | awk '{print $1}' > "${TARBALL}.sha256"
rm -rf "$STAGE"

# Copy bootstrap + installer as standalone assets for one-liner usability.
cp install.sh "$DIST/install.sh"
cp scripts/bootstrap.sh "$DIST/bootstrap.sh"

# Create or update release.
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  echo "[release] Updating existing release $TAG"
  gh release upload "$TAG" \
    "$TARBALL" "${TARBALL}.sha256" "$DIST/install.sh" "$DIST/bootstrap.sh" \
    -R "$REPO" --clobber
else
  echo "[release] Creating release $TAG"
  gh release create "$TAG" \
    "$TARBALL" "${TARBALL}.sha256" "$DIST/install.sh" "$DIST/bootstrap.sh" \
    -R "$REPO" --title "OpenClaw Panel $TAG" --notes "$NOTES"
fi

echo
BOOTSTRAP_ASSET_ID=$(gh api "/repos/$REPO/releases/tags/$TAG" \
  --jq '.assets[] | select(.name=="bootstrap.sh") | .id')

cat <<EOM

[release] Done. One-liner installers:

Public repo (no auth):
  curl -fsSL https://github.com/$REPO/releases/latest/download/bootstrap.sh \\
    | sudo bash -s -- --domain example.com

Private repo (requires PAT with repo:read scope):
  GH_TOKEN=ghp_xxx
  curl -fsSL -H "Authorization: token \$GH_TOKEN" -H "Accept: application/octet-stream" \\
    -o /tmp/bootstrap.sh \\
    "https://api.github.com/repos/$REPO/releases/assets/$BOOTSTRAP_ASSET_ID"
  sudo GH_TOKEN="\$GH_TOKEN" bash /tmp/bootstrap.sh --domain example.com

Pass extra installer flags after --domain (e.g. --no-firewall, --skip-chrome).
EOM
