#!/usr/bin/env bash
# Sync OAuth/auth profiles from the portable agent config dir (where the
# panel's OAuth flow writes) to the daemon's expected agentDir.
#
# Why: OAuth completion writes to /opt/openclaw/config/agents/default/agent/
# but the openclaw daemon (HOME=/opt/openclaw) reads from
# /opt/openclaw/.openclaw/agents/main/agent/. Without this sync, chats fail
# with "No API key found for provider <id>".
#
# Runs as ExecStartPre for openclaw.service. Idempotent — only copies if
# source is newer than dest. Safe to run multiple times.
set -u
SRC=/opt/openclaw/config/agents/default/agent/auth-profiles.json
DST_DIR=/opt/openclaw/.openclaw/agents/main/agent
DST="$DST_DIR/auth-profiles.json"

[[ -f "$SRC" ]] || exit 0  # nothing to sync yet (first boot, no OAuth yet)
mkdir -p "$DST_DIR"
if [[ ! -f "$DST" ]] || [[ "$SRC" -nt "$DST" ]]; then
  cp "$SRC" "$DST"
  chmod 0600 "$DST"
  chown root:root "$DST"
  logger -t openclaw-sync-auth "Synced auth-profiles.json from portable config"
fi
exit 0
