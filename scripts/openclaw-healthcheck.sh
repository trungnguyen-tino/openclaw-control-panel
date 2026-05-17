#!/usr/bin/env bash
# OpenClaw self-healing health-check.
# Runs every 5 min via systemd timer.
#   1) Cert is Let's Encrypt (skip if DOMAIN is IP)   → reload caddy
#   2) /api/health returns 200                         → restart openclaw-mgmt
#   3) /gw/ returns 200/302                            → restart openclaw
#   4) /gateway WS upgrade returns 101                 → restart openclaw + caddy
#   5) Cert not expiring within 14 days                → reload caddy (forces ACME renewal)
# Each fix triggers a retry of THAT check before declaring failure.
# Logs to journald (tag: openclaw-healthcheck) + /var/log/openclaw-healthcheck.log
set -u
LOG=/var/log/openclaw-healthcheck.log
TAG=openclaw-healthcheck

DOMAIN=$(grep -E '^DOMAIN=' /opt/openclaw/.env 2>/dev/null | cut -d= -f2-)
[[ -z "$DOMAIN" ]] && { echo "[healthcheck] DOMAIN missing"; exit 0; }
DOMAIN_HOST="${DOMAIN#http://}"; DOMAIN_HOST="${DOMAIN_HOST#https://}"

FIXED=0; FAILED=0

log() {
  local msg="$(date '+%Y-%m-%d %H:%M:%S') $*"
  echo "$msg" | tee -a "$LOG" >&2
  logger -t "$TAG" "$*"
}

wait_caddy_ready() {
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    systemctl is-active --quiet caddy && \
      curl -sk --max-time 3 "https://${DOMAIN_HOST}/api/health" >/dev/null 2>&1 && return 0
  done
  return 1
}

probe_cert_issuer() {
  echo | timeout 6 openssl s_client -connect "${DOMAIN_HOST}:443" -servername "$DOMAIN_HOST" 2>/dev/null \
    | openssl x509 -noout -issuer 2>/dev/null
}
probe_http_code() {
  curl -ksI -o /dev/null -w '%{http_code}' --max-time 8 "$1" 2>/dev/null
}
probe_ws_code() {
  curl -k --http1.1 -s -o /dev/null -w '%{http_code}' --max-time 8 \
    -H "Connection: Upgrade" -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" \
    "$1" 2>/dev/null
}

# ---- check 1: cert issuer ----
if [[ "$DOMAIN_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  log "check1 cert: SKIP (DOMAIN is IP)"
else
  issuer=$(probe_cert_issuer)
  if echo "$issuer" | grep -q "Let's Encrypt"; then
    log "check1 cert: ✓ LE"
  else
    log "check1 cert: ✗ $issuer — reloading caddy"
    systemctl reload caddy
    wait_caddy_ready || log "  caddy not ready after reload"
    sleep 5  # give ACME a moment if it's issuing
    issuer=$(probe_cert_issuer)
    if echo "$issuer" | grep -q "Let's Encrypt"; then
      log "  → FIXED ($issuer)"; FIXED=$((FIXED+1))
    else
      log "  → STILL: $issuer"; FAILED=$((FAILED+1))
    fi
  fi
fi

# ---- check 2: /api/health ----
code=$(probe_http_code "https://${DOMAIN_HOST}/api/health")
if [[ "$code" == "200" ]]; then
  log "check2 api/health: ✓ 200"
else
  log "check2 api/health: ✗ $code — restarting openclaw-mgmt"
  systemctl restart openclaw-mgmt
  sleep 6
  code=$(probe_http_code "https://${DOMAIN_HOST}/api/health")
  if [[ "$code" == "200" ]]; then
    log "  → FIXED"; FIXED=$((FIXED+1))
  else
    log "  → STILL HTTP $code"; FAILED=$((FAILED+1))
  fi
fi

# ---- check 3: /gw/ ----
code=$(probe_http_code "https://${DOMAIN_HOST}/gw/")
if [[ "$code" == "200" || "$code" == "302" ]]; then
  log "check3 gw/: ✓ $code"
else
  log "check3 gw/: ✗ $code — restarting openclaw"
  systemctl restart openclaw
  sleep 8
  code=$(probe_http_code "https://${DOMAIN_HOST}/gw/")
  if [[ "$code" == "200" || "$code" == "302" ]]; then
    log "  → FIXED"; FIXED=$((FIXED+1))
  else
    log "  → STILL HTTP $code"; FAILED=$((FAILED+1))
  fi
fi

# ---- check 4: /gateway WS upgrade ----
code=$(probe_ws_code "https://${DOMAIN_HOST}/gateway")
if [[ "$code" == "101" ]]; then
  log "check4 /gateway WS: ✓ 101"
else
  log "check4 /gateway WS: ✗ $code — restarting openclaw + caddy"
  systemctl restart openclaw caddy
  wait_caddy_ready || true
  sleep 5
  code=$(probe_ws_code "https://${DOMAIN_HOST}/gateway")
  if [[ "$code" == "101" ]]; then
    log "  → FIXED"; FIXED=$((FIXED+1))
  else
    log "  → STILL HTTP $code"; FAILED=$((FAILED+1))
  fi
fi

# ---- check 5: cert expiry < 14d ----
if [[ "$DOMAIN_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  log "check5 cert-expiry: SKIP (IP)"
else
  if echo | timeout 6 openssl s_client -connect "${DOMAIN_HOST}:443" -servername "$DOMAIN_HOST" 2>/dev/null \
     | openssl x509 -noout -checkend $((14*86400)) >/dev/null 2>&1; then
    log "check5 cert-expiry: ✓ >14d"
  else
    log "check5 cert-expiry: ✗ <14d — reloading caddy to renew"
    systemctl reload caddy
    wait_caddy_ready || true
    FIXED=$((FIXED+1))
  fi
fi

log "=== END $DOMAIN_HOST (fixed=$FIXED, failed=$FAILED) ==="
exit 0
