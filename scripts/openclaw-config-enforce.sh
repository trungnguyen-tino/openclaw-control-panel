#!/usr/bin/env bash
# Enforce required gateway.controlUi flags before openclaw starts.
# Prevents `--allow-unconfigured` from stripping our security flags
# on every restart (observed: dangerouslyDisableDeviceAuth keeps reverting
# to false, basePath/allowedOrigins disappear). Idempotent — safe to run
# multiple times.
set -euo pipefail
CFG="/opt/openclaw/.openclaw/openclaw.json"
[[ -f "$CFG" ]] || exit 0  # first boot — let openclaw init normally
DOMAIN=$(grep -E "^DOMAIN=" /opt/openclaw/.env | cut -d= -f2- || echo "localhost")
DOMAIN_HOST="${DOMAIN#http://}"
DOMAIN_HOST="${DOMAIN_HOST#https://}"
ORIGINS=$(printf '"https://%s","https://%s:18790","http://%s","http://%s:18790"' \
  "$DOMAIN_HOST" "$DOMAIN_HOST" "$DOMAIN_HOST" "$DOMAIN_HOST")
TMP=$(mktemp)
jq ".gateway.controlUi.dangerouslyDisableDeviceAuth = true \
  | .gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback = true \
  | .gateway.controlUi.allowInsecureAuth = true \
  | .gateway.controlUi.enabled = true \
  | .gateway.controlUi.basePath = \"/gw\" \
  | .gateway.controlUi.allowedOrigins = [$ORIGINS]" "$CFG" > "$TMP" || { rm -f "$TMP"; exit 0; }
if ! cmp -s "$CFG" "$TMP"; then
  mv "$TMP" "$CFG"
  chmod 600 "$CFG"
  chown root:root "$CFG"
  logger -t openclaw-config-enforce "Restored required controlUi flags"
else
  rm -f "$TMP"
fi
