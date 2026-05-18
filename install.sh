#!/usr/bin/env bash
# OpenClaw Panel — Ubuntu 22.04/24.04 installer.
#
# One-liner:
#   curl -fsSL <RELEASE_URL>/install.sh | bash -s -- --domain X --mgmt-key Y
#
# Flags:
#   --domain <DOMAIN>          (required) FQDN or http://<IP>
#   --mgmt-key <KEY>           (optional) override generated MGMT API key
#   --tag <vN>                 (optional) release tag (default: latest)
#   --release-base <URL>       (optional) override panel tarball base URL
#   --tarball <PATH>           (optional) install from a local tarball (skip download)
#   --theme <NAME>             (optional) UI theme: "default" (Tino green, the
#                              default) or "ictsaigon" (blue)
#   --admin-user <USER>        (optional) panel admin username (default: admin)
#   --admin-pass <PASS>        (optional) panel admin password (default: admin123)
#   --legacy-routing           (optional) Caddy routes / → gateway (source layout)
#   --no-firewall              (optional) skip ufw configuration
#   --skip-chrome              (optional) skip Google Chrome install
#   --force                    (optional) suppress legacy-detected warnings
#   --auth-header <H>          (optional) extra HTTP header passed to curl when
#                              downloading release assets (e.g. private GitHub
#                              token: --auth-header "Authorization: token PAT")

set -euo pipefail

DOMAIN=""
MGMT_KEY=""
TAG=""
RELEASE_BASE="${OPENCLAW_PANEL_RELEASE_BASE:-}"  # e.g. https://gitlab.com/<user>/<proj>/-/releases
LOCAL_TARBALL=""
LEGACY_ROUTING=0
NO_FIREWALL=0
SKIP_CHROME=0
FORCE=0
AUTH_HEADER=""  # optional `Authorization: token <PAT>` for private GitHub release downloads
THEME="default"  # "default" (Tino green) | "ictsaigon" (blue)
ADMIN_USER="admin"
ADMIN_PASS="admin123"

# Constants
OPENCLAW_HOME=/opt/openclaw
MGMT_DIR=/opt/openclaw-mgmt
LEGACY_DIR_PREFIX=/opt/openclaw-mgmt-legacy-

log()  { printf '\033[1;36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || die "Run as root (use sudo)."
}

parse_flags() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --domain)         DOMAIN="$2"; shift 2 ;;
      --mgmt-key)       MGMT_KEY="$2"; shift 2 ;;
      --tag)            TAG="$2"; shift 2 ;;
      --release-base)   RELEASE_BASE="$2"; shift 2 ;;
      --tarball)        LOCAL_TARBALL="$2"; shift 2 ;;
      --auth-header)    AUTH_HEADER="$2"; shift 2 ;;
      --theme)          THEME="$2"; shift 2 ;;
      --admin-user)     ADMIN_USER="$2"; shift 2 ;;
      --admin-pass)     ADMIN_PASS="$2"; shift 2 ;;
      --legacy-routing) LEGACY_ROUTING=1; shift ;;
      --no-firewall)    NO_FIREWALL=1; shift ;;
      --skip-chrome)    SKIP_CHROME=1; shift ;;
      --force)          FORCE=1; shift ;;
      -h|--help)
        sed -n '2,20p' "$0"; exit 0 ;;
      *) die "Unknown flag: $1" ;;
    esac
  done
  [[ -n "$DOMAIN" ]] || die "--domain required"
  case "$THEME" in
    default|ictsaigon) ;;
    *) die "--theme must be 'default' or 'ictsaigon', got: $THEME" ;;
  esac
}

detect_ubuntu() {
  [[ -r /etc/os-release ]] || die "Not a Linux with /etc/os-release"
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "$ID" == "ubuntu" ]] || die "Only Ubuntu is supported. Detected: ${ID}"
  case "${VERSION_ID:-}" in
    22.04|24.04) UBUNTU_VERSION="$VERSION_ID" ;;
    *) die "Unsupported Ubuntu: ${VERSION_ID}. Need 22.04 or 24.04." ;;
  esac
  log "Detected Ubuntu ${UBUNTU_VERSION}"
}

disable_unattended_upgrades() {
  log "Stopping unattended-upgrades"
  systemctl stop unattended-upgrades 2>/dev/null || true
  systemctl disable unattended-upgrades 2>/dev/null || true
  for lock in /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock; do
    fuser -k -TERM "$lock" 2>/dev/null || true
  done
}

apt_update_with_retry() {
  for i in 1 2 3; do
    apt-get update -qq && return 0
    warn "apt-get update failed (try $i/3) — sleeping"
    sleep 5
  done
  die "apt-get update failed after 3 tries"
}

install_base_packages() {
  log "Installing base packages"
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    curl ca-certificates gnupg ufw fail2ban jq dnsutils tar
}

install_nodejs() {
  if command -v node >/dev/null 2>&1; then
    log "Node.js already installed ($(node --version))"
    return
  fi
  log "Installing Node.js 24"
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
}

install_openclaw_npm() {
  if command -v openclaw >/dev/null 2>&1; then
    log "OpenClaw npm already installed"
  else
    log "Installing openclaw npm package"
    npm install -g openclaw@latest
  fi
}

install_python_312() {
  # Ubuntu 24.04 ships python3.12 binary but `ensurepip` (needed for venv
  # with pip) lives in python3.12-venv / python3-venv. Always verify
  # `ensurepip` works — that's what venv actually requires.
  if command -v python3.12 >/dev/null 2>&1 && python3.12 -c "import ensurepip" 2>/dev/null; then
    log "Python 3.12 + venv already installed"
    return
  fi
  log "Installing Python 3.12 (Ubuntu ${UBUNTU_VERSION})"
  if [[ "$UBUNTU_VERSION" == "22.04" ]]; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt_update_with_retry
  fi
  # Install both -venv variants (the .12-suffixed package and the plain one)
  # — Ubuntu 24.04 sometimes ships them as separate packages.
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.12 python3.12-venv python3.12-dev python3-venv python3-dev || true
  # Verify the install actually fixed ensurepip; otherwise fail loudly.
  python3.12 -c "import ensurepip" 2>/dev/null \
    || die "Python 3.12 venv setup failed — ensurepip still missing after apt install"
}

install_chrome() {
  if [[ "$SKIP_CHROME" == "1" ]]; then
    log "Skipping Chrome (--skip-chrome)"
    return
  fi
  if [[ -x /opt/google/chrome/chrome ]]; then
    log "Chrome already installed"
    return
  fi
  log "Installing Google Chrome"
  local deb=/tmp/google-chrome-stable.deb
  if curl -fsSL -o "$deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$deb" || warn "Chrome install failed; continuing"
    rm -f "$deb"
  else
    warn "Chrome download failed; continuing without"
  fi
}

install_caddy() {
  if command -v caddy >/dev/null 2>&1; then
    log "Caddy already installed"
    return
  fi
  log "Installing Caddy"
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt_update_with_retry
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy
}

configure_firewall() {
  if [[ "$NO_FIREWALL" == "1" ]]; then
    log "Skipping UFW (--no-firewall)"
    return
  fi
  log "Configuring UFW"
  ufw --force default deny incoming
  ufw --force default allow outgoing
  ufw allow OpenSSH || true
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw allow 9998/tcp
  ufw --force enable
}

backup_legacy_mgmt() {
  if [[ -f "$MGMT_DIR/server.js" ]]; then
    local ts; ts=$(date +%s)
    local dest="${LEGACY_DIR_PREFIX}${ts}"
    if [[ "$FORCE" != "1" ]]; then
      warn "Legacy Node mgmt-api detected at $MGMT_DIR/server.js"
      warn "Backing up to $dest (use --force to suppress this notice)"
    fi
    mv "$MGMT_DIR" "$dest"
  fi
}

fetch_and_extract_panel() {
  local tmp=/tmp/openclaw-panel.tar.gz
  if [[ -n "$LOCAL_TARBALL" ]]; then
    log "Using local tarball: $LOCAL_TARBALL"
    [[ -f "$LOCAL_TARBALL" ]] || die "Tarball not found at $LOCAL_TARBALL"
    # Skip copy if caller already placed the file at our staging path.
    if [[ "$(readlink -f "$LOCAL_TARBALL")" != "$(readlink -f "$tmp" 2>/dev/null || echo "$tmp")" ]]; then
      cp "$LOCAL_TARBALL" "$tmp"
    fi
    if [[ -f "${LOCAL_TARBALL}.sha256" ]] && [[ "$(readlink -f "${LOCAL_TARBALL}.sha256")" != "$(readlink -f "${tmp}.sha256" 2>/dev/null || echo "${tmp}.sha256")" ]]; then
      cp "${LOCAL_TARBALL}.sha256" "${tmp}.sha256"
    fi
  else
    log "Fetching openclaw-panel tarball"
    if [[ -z "$RELEASE_BASE" ]]; then
      die "OPENCLAW_PANEL_RELEASE_BASE not set. Use --release-base <URL>, --tarball <PATH>, or set env var."
    fi
    # Naming: GitHub releases/latest/download/openclaw-panel.tar.gz (preferred)
    # or legacy openclaw-panel-<tag>.tar.gz when --tag is passed.
    local tarball_url
    if [[ -n "$TAG" ]]; then
      tarball_url="${RELEASE_BASE}/openclaw-panel-${TAG}.tar.gz"
    else
      tarball_url="${RELEASE_BASE}/openclaw-panel.tar.gz"
    fi
    local sha_url="${tarball_url}.sha256"
    local curl_auth=()
    [[ -n "$AUTH_HEADER" ]] && curl_auth=(-H "$AUTH_HEADER")
    for i in 1 2 3; do
      if curl -fsSL "${curl_auth[@]}" -o "$tmp" "$tarball_url"; then break; fi
      warn "Download failed (try $i/3); retrying"
      sleep 3
    done
    [[ -f "$tmp" ]] || die "Tarball download failed: $tarball_url"
    curl -fsSL "${curl_auth[@]}" -o "${tmp}.sha256" "$sha_url" 2>/dev/null || true
  fi
  if [[ -f "${tmp}.sha256" ]]; then
    local expected; expected=$(awk '{print $1}' "${tmp}.sha256")
    local actual; actual=$(sha256sum "$tmp" | awk '{print $1}')
    [[ "$expected" == "$actual" ]] || die "sha256 mismatch (expected=$expected got=$actual)"
    log "Checksum verified"
  else
    warn "No .sha256 sibling found; skipping checksum"
  fi
  mkdir -p "$MGMT_DIR"
  tar -xzf "$tmp" -C "$MGMT_DIR" --strip-components=1
  rm -f "$tmp" "${tmp}.sha256"
}

setup_venv() {
  log "Creating Python venv"
  python3.12 -m venv "$MGMT_DIR/.venv"
  "$MGMT_DIR/.venv/bin/pip" install --quiet --upgrade pip wheel
  "$MGMT_DIR/.venv/bin/pip" install --quiet -r "$MGMT_DIR/requirements.txt"
}

generate_env_if_absent() {
  if [[ -f "$OPENCLAW_HOME/.env" ]]; then
    log ".env already exists — preserving"
    return
  fi
  log "Generating fresh .env"
  mkdir -p "$OPENCLAW_HOME/config/devices" "$OPENCLAW_HOME/config/agents" "$OPENCLAW_HOME/data" "$OPENCLAW_HOME/.openclaw"
  local gateway_token; gateway_token=$(openssl rand -hex 32)
  local mgmt_key="${MGMT_KEY:-$(openssl rand -hex 32)}"
  local ram_mb; ram_mb=$(awk '/MemTotal/{printf "%d", $2/1024 * 0.8}' /proc/meminfo)
  local caddy_tls=""
  # If DOMAIN looks like an IP / http://, use self-signed.
  if [[ "$DOMAIN" == http* ]] || [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    caddy_tls="tls internal"
  fi
  # Default OPENCLAW_PANEL_RELEASE_URL points at the GitHub Releases asset
  # pattern that publish-github-release.sh produces. Self-update UI uses it.
  local release_url="${OPENCLAW_PANEL_RELEASE_URL:-https://github.com/trungnguyen-tino/openclaw-panel/releases/download/{tag}/openclaw-panel.tar.gz}"
  cat > "$OPENCLAW_HOME/.env" <<EOF
OPENCLAW_VERSION=latest
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_GATEWAY_TOKEN=${gateway_token}
DOMAIN=${DOMAIN}
CADDY_TLS=${caddy_tls}
OPENCLAW_MGMT_API_KEY=${mgmt_key}
NODE_OPTIONS=--max-old-space-size=${ram_mb}
OPENCLAW_PANEL_RELEASE_URL=${release_url}
OPENCLAW_THEME=${THEME}
EOF
  # Compute scrypt hash for the admin password using stdlib (matches app/auth.py).
  # Falls back to system python3 if the venv isn't built yet.
  local py="$MGMT_DIR/.venv/bin/python3"
  [[ -x "$py" ]] || py="$(command -v python3.12 || command -v python3)"
  local admin_hash
  admin_hash=$("$py" - <<PYEOF
import hashlib, secrets
salt = secrets.token_bytes(16)
d = hashlib.scrypt(b"${ADMIN_PASS}", salt=salt, n=16384, r=8, p=1, dklen=64)
print(f"{salt.hex()}:{d.hex()}")
PYEOF
)
  cat >> "$OPENCLAW_HOME/.env" <<EOF
OPENCLAW_LOGIN_USER=${ADMIN_USER}
OPENCLAW_LOGIN_PASS=${admin_hash}
EOF
  chmod 0600 "$OPENCLAW_HOME/.env"
  echo "${mgmt_key}" > /tmp/openclaw-mgmt-key.txt
  chmod 0600 /tmp/openclaw-mgmt-key.txt
}

install_provider_templates() {
  # Copy templates only if /etc/openclaw/config/ is empty (preserve user edits).
  mkdir -p /etc/openclaw/config
  if [[ -z "$(ls -A /etc/openclaw/config/ 2>/dev/null)" ]]; then
    log "Copying provider templates to /etc/openclaw/config/"
    cp -n "$MGMT_DIR"/app/providers/templates/*.json /etc/openclaw/config/ || true
  else
    log "/etc/openclaw/config/ already populated — preserving"
  fi
}

write_caddyfile() {
  log "Writing Caddyfile"
  if [[ "$LEGACY_ROUTING" == "1" ]]; then
    cat > "$OPENCLAW_HOME/Caddyfile" <<'EOF'
{$DOMAIN:localhost} {
    {$CADDY_TLS:tls internal}
    handle /login {
        reverse_proxy 127.0.0.1:9998
    }
    handle /api/auth/* {
        reverse_proxy 127.0.0.1:9998
    }
    reverse_proxy 127.0.0.1:18789 {
        header_up Host "localhost:18789"
    }
}
EOF
  else
    cp "$MGMT_DIR/app/caddy/Caddyfile.template" "$OPENCLAW_HOME/Caddyfile"
  fi
  chmod 0644 "$OPENCLAW_HOME/Caddyfile"
  ln -sfn "$OPENCLAW_HOME/config" "$OPENCLAW_HOME/.openclaw"
}

write_systemd_units() {
  log "Writing systemd units"
  cp "$MGMT_DIR/systemd/openclaw.service" /etc/systemd/system/openclaw.service
  cp "$MGMT_DIR/systemd/openclaw-mgmt.service" /etc/systemd/system/openclaw-mgmt.service
  mkdir -p /etc/systemd/system/caddy.service.d
  cp "$MGMT_DIR/systemd/caddy-override.conf" /etc/systemd/system/caddy.service.d/override.conf

  # Install config-enforce hook — openclaw `--allow-unconfigured` strips our
  # security flags on every restart, so we re-apply them via ExecStartPre.
  install -m 0755 "$MGMT_DIR/scripts/openclaw-config-enforce.sh" \
    /usr/local/bin/openclaw-config-enforce.sh 2>/dev/null || true
  # Install auth-profiles sync hook — OAuth writes to portable agent dir but
  # daemon reads from .openclaw/agents/main/agent; this re-syncs on startup.
  install -m 0755 "$MGMT_DIR/scripts/openclaw-sync-auth-profiles.sh" \
    /usr/local/bin/openclaw-sync-auth-profiles.sh 2>/dev/null || true
  mkdir -p /etc/systemd/system/openclaw.service.d
  cat > /etc/systemd/system/openclaw.service.d/enforce.conf <<'EOF'
[Service]
ExecStartPre=/usr/local/bin/openclaw-sync-auth-profiles.sh
ExecStartPre=/usr/local/bin/openclaw-config-enforce.sh
EOF

  # Self-healing health-check (5-min systemd timer) — auto-fixes cert / api /
  # gw / gateway WS issues without paging a human.
  install -m 0755 "$MGMT_DIR/scripts/openclaw-healthcheck.sh" \
    /usr/local/bin/openclaw-healthcheck.sh 2>/dev/null || true
  cp "$MGMT_DIR/systemd/openclaw-healthcheck.service" /etc/systemd/system/openclaw-healthcheck.service 2>/dev/null || true
  cp "$MGMT_DIR/systemd/openclaw-healthcheck.timer" /etc/systemd/system/openclaw-healthcheck.timer 2>/dev/null || true

  systemctl daemon-reload
  systemctl enable openclaw caddy openclaw-mgmt >/dev/null
  systemctl enable --now openclaw-healthcheck.timer >/dev/null 2>&1 || true
}

init_openclaw_config() {
  # OpenClaw npm fails to start on empty/invalid `.openclaw/openclaw.json`.
  # `doctor --fix` initializes a clean schema; safe to run idempotently.
  local cfg="$OPENCLAW_HOME/.openclaw/openclaw.json"
  mkdir -p "$(dirname "$cfg")"
  if [[ ! -s "$cfg" ]]; then
    log "Initializing openclaw config via doctor --fix"
    HOME="$OPENCLAW_HOME" \
      OPENCLAW_GATEWAY_TOKEN="$(grep -E '^OPENCLAW_GATEWAY_TOKEN=' "$OPENCLAW_HOME/.env" | cut -d= -f2-)" \
      openclaw doctor --fix >/dev/null 2>&1 || warn "openclaw doctor --fix failed; gateway may not start"
  fi
  # Add Control UI origin allowlist for the panel's domain — required because
  # openclaw rejects external origins by default even behind the reverse proxy.
  if [[ -s "$cfg" ]] && command -v jq >/dev/null 2>&1; then
    local domain_host="$DOMAIN"
    domain_host="${domain_host#http://}"
    domain_host="${domain_host#https://}"
    local origins
    origins=$(printf '"https://%s","https://%s:18790","http://%s","http://%s:18790"' \
      "$domain_host" "$domain_host" "$domain_host" "$domain_host")
    local patched
    patched=$(jq ".gateway.controlUi.allowedOrigins = [${origins}] \
      | .gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback = true \
      | .gateway.controlUi.allowInsecureAuth = true \
      | .gateway.controlUi.dangerouslyDisableDeviceAuth = true \
      | .gateway.controlUi.basePath = \"/gw\" \
      | .gateway.controlUi.enabled = true" "$cfg") || true
    if [[ -n "$patched" ]]; then
      printf '%s\n' "$patched" > "$cfg"
      chmod 0600 "$cfg"
    fi
  fi
}

start_services() {
  log "Starting services"
  systemctl restart caddy
  systemctl restart openclaw || warn "openclaw failed to start; check journalctl"
  systemctl restart openclaw-mgmt
}

health_check() {
  log "Health check (up to 30s)..."
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:9998/api/health >/dev/null 2>&1; then
      log "Management API healthy"
      return
    fi
    sleep 1
  done
  warn "Management API failed health check — see: journalctl -u openclaw-mgmt -n 50"
}

print_summary() {
  local domain mgmt_key admin_user
  domain=$(grep -E '^DOMAIN=' "$OPENCLAW_HOME/.env" | cut -d= -f2-)
  mgmt_key=$(grep -E '^OPENCLAW_MGMT_API_KEY=' "$OPENCLAW_HOME/.env" | cut -d= -f2-)
  admin_user=$(grep -E '^OPENCLAW_LOGIN_USER=' "$OPENCLAW_HOME/.env" | cut -d= -f2-)
  cat <<EOF

===============================================================================
  OpenClaw Panel installed.
-------------------------------------------------------------------------------
  Domain        : ${domain}
  Dashboard URL : https://${domain}/
  Login         : ${admin_user} / ${ADMIN_PASS}     (tab "Tài khoản")
  MGMT API key  : ${mgmt_key}                       (tab "API Key")
  Services      : openclaw / caddy / openclaw-mgmt
  Logs          : journalctl -u openclaw-mgmt -f
===============================================================================
EOF
}

main() {
  parse_flags "$@"
  require_root
  detect_ubuntu
  disable_unattended_upgrades
  apt_update_with_retry
  install_base_packages
  install_nodejs
  install_openclaw_npm
  install_chrome
  install_caddy
  configure_firewall
  install_python_312
  backup_legacy_mgmt
  fetch_and_extract_panel
  setup_venv
  generate_env_if_absent
  install_provider_templates
  write_caddyfile
  write_systemd_units
  init_openclaw_config
  start_services
  health_check
  print_summary
}

main "$@"
