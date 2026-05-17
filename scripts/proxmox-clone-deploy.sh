#!/usr/bin/env bash
# proxmox-clone-deploy.sh — Clone OpenClaw template VM + auto-install panel.
#
# Run ON THE PROXMOX HOST as root (or member of PVEAdmin).
#
# Usage:
#   bash proxmox-clone-deploy.sh \
#     --template 9000 \
#     --vmid 200 \
#     --name openclaw-prod \
#     --domain openclaw.example.com \
#     --ip 192.168.1.50/24 \
#     --gw 192.168.1.1 \
#     --ssh-key "~/.ssh/id_rsa.pub" \
#     --gh-token ghp_xxx \
#     [--bridge vmbr0] [--cores 2] [--memory 2048] [--disk-size 32G]
#
# Prerequisites on Proxmox host:
# - Template VM (id e.g. 9000) created from Ubuntu 24.04 cloud image:
#     wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
#     qm create 9000 --memory 2048 --net0 virtio,bridge=vmbr0 --name ubuntu-2404-template
#     qm importdisk 9000 noble-server-cloudimg-amd64.img local-lvm
#     qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
#     qm set 9000 --ide2 local-lvm:cloudinit
#     qm set 9000 --boot c --bootdisk scsi0
#     qm set 9000 --serial0 socket --vga serial0
#     qm set 9000 --agent enabled=1
#     qm template 9000
#
# What this script does:
# 1. qm clone <template> <vmid>
# 2. Generate per-VM cloud-init user-data from snippet template
# 3. qm set --cicustom + --ipconfig0 + --sshkey + --ciuser
# 4. qm start <vmid>
# 5. Wait for SSH + tail /var/log/openclaw-install.log

set -euo pipefail

TEMPLATE=""
VMID=""
NAME=""
DOMAIN=""
IP=""
GATEWAY=""
SSH_KEY=""
GH_TOKEN=""
BRIDGE="vmbr0"
CORES="2"
MEMORY="2048"
DISK_SIZE="32G"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template)   TEMPLATE="$2"; shift 2 ;;
    --vmid)       VMID="$2"; shift 2 ;;
    --name)       NAME="$2"; shift 2 ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --ip)         IP="$2"; shift 2 ;;
    --gw)         GATEWAY="$2"; shift 2 ;;
    --ssh-key)    SSH_KEY="$2"; shift 2 ;;
    --gh-token)   GH_TOKEN="$2"; shift 2 ;;
    --bridge)     BRIDGE="$2"; shift 2 ;;
    --cores)      CORES="$2"; shift 2 ;;
    --memory)     MEMORY="$2"; shift 2 ;;
    --disk-size)  DISK_SIZE="$2"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

for v in TEMPLATE VMID NAME DOMAIN IP GATEWAY SSH_KEY GH_TOKEN; do
  [[ -z "${!v}" ]] && { echo "Missing --${v,,}" >&2; exit 1; }
done

log() { printf '\033[1;36m[clone]\033[0m %s\n' "$*"; }

# Resolve current bootstrap asset ID from GitHub (auto-update for new releases).
log "Fetching bootstrap asset ID from GitHub..."
BOOTSTRAP_ID=$(curl -fsSL \
  -H "Authorization: token $GH_TOKEN" \
  "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/latest" \
  | grep -A 4 '"name": "bootstrap.sh"' | grep '"id":' | head -1 | grep -oE '[0-9]+')
[[ -z "$BOOTSTRAP_ID" ]] && { echo "Failed to resolve bootstrap.sh asset ID" >&2; exit 1; }
log "BOOTSTRAP_ID=$BOOTSTRAP_ID"

# Generate per-VM cloud-init snippet.
SNIPPET_PATH="/var/lib/vz/snippets/openclaw-${VMID}.yaml"
PUB_KEY=$(cat "$SSH_KEY")

log "Writing cloud-init snippet: $SNIPPET_PATH"
cat > "$SNIPPET_PATH" <<EOF
#cloud-config
hostname: ${NAME}
manage_etc_hosts: true
ssh_authorized_keys:
  - ${PUB_KEY}
package_update: true
packages: [curl, ca-certificates]
runcmd:
  - export GH_TOKEN='${GH_TOKEN}'
  - >
    curl -fsSL
    -H "Authorization: token \$GH_TOKEN"
    -H "Accept: application/octet-stream"
    -o /tmp/bootstrap.sh
    "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/assets/${BOOTSTRAP_ID}"
  - chmod +x /tmp/bootstrap.sh
  - >
    setsid bash -c "GH_TOKEN='\$GH_TOKEN' bash /tmp/bootstrap.sh
    --domain ${DOMAIN} --no-firewall --skip-chrome --force
    > /var/log/openclaw-install.log 2>&1" &
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
  --sshkeys <(echo "$PUB_KEY") \
  --ciuser root \
  --cicustom "user=local:snippets/openclaw-${VMID}.yaml"

log "Starting VM $VMID"
qm start "$VMID"

log "Done. Watch progress with:"
echo "  ssh root@${IP%/*} 'tail -f /var/log/openclaw-install.log'"
echo "  Panel will be at: https://${DOMAIN}/"
