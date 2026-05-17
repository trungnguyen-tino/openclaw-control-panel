#!/usr/bin/env bash
# OpenClaw Panel one-liner bootstrap.
#
# Public repo:
#   curl -fsSL https://github.com/OWNER/openclaw-panel/releases/latest/download/bootstrap.sh \
#     | bash -s -- --domain example.com
#
# Private repo (requires GH personal access token with `repo:read`):
#   GH_TOKEN="ghp_xxx" \
#   curl -fsSL -H "Authorization: token $GH_TOKEN" \
#     -o /tmp/bootstrap.sh \
#     "https://api.github.com/repos/OWNER/openclaw-panel/releases/latest/assets/<bootstrap-asset-id>" \
#     -H "Accept: application/octet-stream" && \
#   GH_TOKEN="$GH_TOKEN" bash /tmp/bootstrap.sh --domain example.com
#
# The bootstrap fetches install.sh + tarball (auto-resolving asset IDs when
# `$GH_TOKEN` is set), then runs the installer with the right flags.

set -euo pipefail

OWNER_REPO="${OPENCLAW_PANEL_REPO:-trungnguyen-tino/openclaw-control-panel}"
DOMAIN=""
EXTRA_FLAGS=()

# Parse flags — everything after --domain goes to install.sh.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --repo)   OWNER_REPO="$2"; shift 2 ;;
    *)        EXTRA_FLAGS+=("$1"); shift ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "usage: bootstrap.sh --domain <DOMAIN-or-IP> [--repo OWNER/REPO] [extra install.sh flags]" >&2
  echo "(For private repo, set GH_TOKEN env var to a PAT with repo:read.)" >&2
  exit 1
fi

# Bootstrap-side curl auth.
AUTH_FLAGS=()
INSTALLER_AUTH=()
if [[ -n "${GH_TOKEN:-}" ]]; then
  AUTH_FLAGS=(-H "Authorization: token $GH_TOKEN" -H "Accept: application/octet-stream")
  INSTALLER_AUTH=(--auth-header "Authorization: token $GH_TOKEN")
fi

API_BASE="https://api.github.com/repos/$OWNER_REPO/releases/latest"

resolve_asset_url() {
  local name="$1"
  if [[ -n "${GH_TOKEN:-}" ]]; then
    # Private repo: use api URL with asset ID for proper redirect handling.
    local id
    id=$(curl -fsSL -H "Authorization: token $GH_TOKEN" "$API_BASE" \
      | python3 -c "import json,sys; r=json.load(sys.stdin); print([a['id'] for a in r['assets'] if a['name']=='$name'][0])")
    echo "https://api.github.com/repos/$OWNER_REPO/releases/assets/$id"
  else
    # Public repo: direct browser_download_url works.
    echo "https://github.com/$OWNER_REPO/releases/latest/download/$name"
  fi
}

INSTALL_URL=$(resolve_asset_url install.sh)
echo "[bootstrap] Resolved install.sh: $INSTALL_URL"

curl -fsSL "${AUTH_FLAGS[@]}" -o /tmp/openclaw-install.sh "$INSTALL_URL"
chmod +x /tmp/openclaw-install.sh

# Tarball release-base = API assets dir if private; latest/download dir if public.
if [[ -n "${GH_TOKEN:-}" ]]; then
  # install.sh expects <RELEASE_BASE>/openclaw-panel.tar.gz to download. With
  # API URL pattern, we need a different scheme. So pre-download the tarball
  # and pass via --tarball instead.
  TAR_URL=$(resolve_asset_url openclaw-panel.tar.gz)
  SHA_URL=$(resolve_asset_url openclaw-panel.tar.gz.sha256)
  echo "[bootstrap] Pre-fetching tarball (private repo)…"
  curl -fsSL "${AUTH_FLAGS[@]}" -o /tmp/openclaw-panel.tar.gz "$TAR_URL"
  curl -fsSL "${AUTH_FLAGS[@]}" -o /tmp/openclaw-panel.tar.gz.sha256 "$SHA_URL"
  exec bash /tmp/openclaw-install.sh \
    --domain "$DOMAIN" \
    --tarball /tmp/openclaw-panel.tar.gz \
    "${EXTRA_FLAGS[@]}"
else
  exec bash /tmp/openclaw-install.sh \
    --domain "$DOMAIN" \
    --release-base "https://github.com/$OWNER_REPO/releases/latest/download" \
    "${EXTRA_FLAGS[@]}"
fi
