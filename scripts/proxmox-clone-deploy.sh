#!/usr/bin/env bash
# proxmox-clone-deploy.sh — Clone OpenClaw template VM + auto-install panel.
#
# Run ON THE PROXMOX HOST as root (or member of PVEAdmin).
#
# One-liner (public repo, no auth):
#   bash <(curl -fsSL https://raw.githubusercontent.com/trungnguyen-tino/openclaw-control-panel/main/scripts/proxmox-clone-deploy.sh) \
#     --template 9001 --vmid 207 --name openclaw-vm-7 \
#     --domain 192.168.232.7 --ip 192.168.232.7/24 --gw 192.168.232.1 \
#     --theme ictsaigon
#
# Root password defaults to ICTsaigon@#2026 — override with --root-pass 'NEW'.
#
# Prerequisites on Proxmox host:
# - Template VM (e.g. 9001) created from Ubuntu 24.04 cloud image. The
#   community helper script does this in one go:
#     bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/vm/ubuntu2404-vm.sh)"
#   then `qm template <id>`.
#
# What this script does:
# 1. qm clone <template> <vmid> --full
# 2. Generate per-VM cloud-init snippet that auto-runs bootstrap.sh
# 3. qm set --cicustom + --ipconfig0 + --sshkeys + --ciuser
# 4. qm start <vmid>
# 5. Print SSH command to tail install log

set -euo pipefail

TEMPLATE=""
VMID=""
NAME=""
DOMAIN=""
IP=""
GATEWAY=""
ROOT_PASS="ICTsaigon@#2026"  # default — override with --root-pass
ADMIN_USER="admin"
ADMIN_PASS="admin123"        # default — override with --admin-pass
THEME="default"
GH_TOKEN=""            # optional — only set for private repo install source
BRIDGE="vmbr0"
CORES="2"
MEMORY="4096"
DISK_SIZE="32G"
REPO="trungnguyen-tino/openclaw-control-panel"
EXTRA_INSTALL_FLAGS="--no-firewall --skip-chrome --force"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template)   TEMPLATE="$2"; shift 2 ;;
    --vmid)       VMID="$2"; shift 2 ;;
    --name)       NAME="$2"; shift 2 ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --ip)         IP="$2"; shift 2 ;;
    --gw)         GATEWAY="$2"; shift 2 ;;
    --root-pass)  ROOT_PASS="$2"; shift 2 ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --admin-pass) ADMIN_PASS="$2"; shift 2 ;;
    --theme)      THEME="$2"; shift 2 ;;
    --gh-token)   GH_TOKEN="$2"; shift 2 ;;
    --bridge)     BRIDGE="$2"; shift 2 ;;
    --cores)      CORES="$2"; shift 2 ;;
    --memory)     MEMORY="$2"; shift 2 ;;
    --disk-size)  DISK_SIZE="$2"; shift 2 ;;
    --repo)       REPO="$2"; shift 2 ;;
    --extra)      EXTRA_INSTALL_FLAGS="$2"; shift 2 ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

for v in TEMPLATE VMID NAME DOMAIN IP GATEWAY ROOT_PASS; do
  [[ -z "${!v}" ]] && { echo "Missing --${v,,}" >&2; exit 1; }
done

case "$THEME" in
  default|ictsaigon) ;;
  *) echo "--theme must be default | ictsaigon (got: $THEME)" >&2; exit 1 ;;
esac

log() { printf '\033[1;36m[clone]\033[0m %s\n' "$*"; }

# Build the bootstrap fetch + run snippet. Public-repo path uses the stable
# /releases/latest/download URL (no asset-ID lookup); private-repo path needs
# a PAT to resolve the bootstrap asset id from the GitHub API.
if [[ -n "$GH_TOKEN" ]]; then
  log "Private-repo mode — resolving bootstrap asset ID with PAT"
  BOOTSTRAP_ID=$(curl -fsSL \
    -H "Authorization: token $GH_TOKEN" \
    "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(next(a['id'] for a in r['assets'] if a['name']=='bootstrap.sh'))")
  FETCH_BLOCK=$(cat <<EOFETCH
  - export GH_TOKEN='${GH_TOKEN}'
  - >
    curl -fsSL
    -H "Authorization: token \$GH_TOKEN"
    -H "Accept: application/octet-stream"
    -o /tmp/bootstrap.sh
    "https://api.github.com/repos/${REPO}/releases/assets/${BOOTSTRAP_ID}"
  - chmod +x /tmp/bootstrap.sh
  - >
    setsid bash -c "GH_TOKEN='\$GH_TOKEN' bash /tmp/bootstrap.sh
    --domain ${DOMAIN} --theme ${THEME} ${EXTRA_INSTALL_FLAGS}
    > /var/log/openclaw-install.log 2>&1" &
EOFETCH
)
else
  log "Public-repo mode — using /releases/latest/download (no auth)"
  FETCH_BLOCK=$(cat <<EOFETCH
  - >
    curl -fsSL -o /tmp/bootstrap.sh
    "https://github.com/${REPO}/releases/latest/download/bootstrap.sh"
  - chmod +x /tmp/bootstrap.sh
  - >
    setsid bash -c "bash /tmp/bootstrap.sh
    --domain ${DOMAIN} --theme ${THEME}
    --admin-user '${ADMIN_USER}' --admin-pass '${ADMIN_PASS}'
    ${EXTRA_INSTALL_FLAGS}
    > /var/log/openclaw-install.log 2>&1" &
EOFETCH
)
fi

# Ensure 'local' storage allows snippets content + the snippets directory
# exists. Fresh Proxmox installs don't enable snippets on 'local' by default,
# and the /var/lib/vz/snippets/ directory is created lazily.
if ! pvesm status -content snippets 2>/dev/null | awk 'NR>1{print $1}' | grep -qx local; then
  log "Enabling 'snippets' content on storage 'local'"
  CURRENT_CONTENT=$(pvesm status -storage local | awk 'NR>1{print $2}' | head -1)
  pvesm set local --content "iso,vztmpl,backup,snippets" || true
fi
mkdir -p /var/lib/vz/snippets

SNIPPET_PATH="/var/lib/vz/snippets/openclaw-${VMID}.yaml"
log "Writing cloud-init snippet: $SNIPPET_PATH"
cat > "$SNIPPET_PATH" <<EOF
#cloud-config
hostname: ${NAME}
manage_etc_hosts: true
# Root password login (no SSH key). Disable cloud-init password expiry so the
# fixed password works on first login.
password: ${ROOT_PASS}
chpasswd:
  expire: false
ssh_pwauth: true
disable_root: false
package_update: true
packages: [curl, ca-certificates]
runcmd:
${FETCH_BLOCK}
  - echo "OpenClaw bootstrap launched. Tail /var/log/openclaw-install.log" > /etc/motd
timezone: Asia/Ho_Chi_Minh
EOF

# Clone + configure.
log "Cloning template $TEMPLATE → VM $VMID ($NAME)"
qm clone "$TEMPLATE" "$VMID" --name "$NAME" --full
qm resize "$VMID" scsi0 "$DISK_SIZE" 2>/dev/null || log "resize skipped (already that size)"
qm set "$VMID" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --net0 "virtio,bridge=$BRIDGE" \
  --ipconfig0 "ip=$IP,gw=$GATEWAY" \
  --ciuser root \
  --cipassword "$ROOT_PASS" \
  --cicustom "user=local:snippets/openclaw-${VMID}.yaml"

log "Starting VM $VMID"
qm start "$VMID"

IP_ONLY="${IP%/*}"
cat <<EOF
[clone] Done. VM is booting + bootstrapping (3–6 min). Watch progress:

  ssh root@${IP_ONLY} 'tail -f /var/log/openclaw-install.log'   (root password: ${ROOT_PASS})

Once installed:
  URL    : https://${DOMAIN}/        (theme=${THEME})
  Login  : ${ADMIN_USER} / ${ADMIN_PASS}      (tab "Tài khoản" on /login)
EOF
