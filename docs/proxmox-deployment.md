# Proxmox VE — Clone Template + Auto-Install OpenClaw Panel

Mô tả 3 cách để clone Proxmox VM template và tự cài OpenClaw Panel, từ thủ công tới full automation.

---

## Tổng quan 3 cách

| Approach | Complexity | Use case |
|---|---|---|
| **A. Cloud-init (recommended)** | ⭐⭐ | Standard. 1 template + per-VM cloud-init user-data |
| **B. Pre-install + snapshot template** | ⭐ | Template đã có panel sẵn → clone là chạy ngay |
| **C. First-boot systemd service** | ⭐⭐⭐ | Không cần Proxmox cloud-init module |

**Khuyên dùng: Approach A.** Standard Proxmox flow, dễ debug, không cần re-bake template khi update panel.

---

## Approach A — Cloud-init (recommended)

### Bước 1: Tạo Ubuntu 24.04 template (1 lần duy nhất)

Trên Proxmox host (`pvesh` / `qm`):

```bash
# Download Ubuntu 24.04 cloud image
cd /var/lib/vz/template/iso
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img

# Tạo VM stub (VMID 9000)
qm create 9000 \
  --memory 2048 \
  --cores 2 \
  --net0 virtio,bridge=vmbr0 \
  --name ubuntu-2404-cloud-template \
  --serial0 socket \
  --vga serial0 \
  --agent enabled=1

# Import disk vào storage `local-lvm` (đổi nếu storage khác)
qm importdisk 9000 noble-server-cloudimg-amd64.img local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --boot c --bootdisk scsi0

# Convert thành template
qm template 9000
```

### Bước 2: Lấy `BOOTSTRAP_ASSET_ID` (mỗi khi release v.X.Y.Z mới)

```bash
GH_TOKEN=ghp_xxx
curl -fsSL -H "Authorization: token $GH_TOKEN" \
  "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/latest" \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print([a['id'] for a in r['assets'] if a['name']=='bootstrap.sh'][0])"
```

Output ví dụ: `421858730`. Ghi nhớ — dùng cho mọi clone tới khi release mới.

### Bước 3: Clone + deploy (mỗi VM mới)

**Cách dễ nhất — dùng script wrapper:**

```bash
# Copy proxmox-clone-deploy.sh lên Proxmox host
scp scripts/proxmox-clone-deploy.sh root@proxmox-host:/root/

# Chạy
ssh root@proxmox-host
bash /root/proxmox-clone-deploy.sh \
  --template 9000 \
  --vmid 200 \
  --name openclaw-prod \
  --domain openclaw.example.com \
  --ip 192.168.1.50/24 \
  --gw 192.168.1.1 \
  --ssh-key ~/.ssh/id_rsa.pub \
  --gh-token ghp_xxx \
  --memory 4096 \
  --cores 2 \
  --disk-size 50G
```

Script:
1. Resolve current `bootstrap.sh` asset ID từ GitHub
2. Generate per-VM cloud-init snippet tại `/var/lib/vz/snippets/openclaw-200.yaml`
3. Clone template → VMID 200
4. Set network, SSH key, cloud-init user-data
5. Start VM

**Theo dõi cài đặt:**
```bash
ssh root@192.168.1.50 'tail -f /var/log/openclaw-install.log'
```

Sau ~3-5 phút (apt + npm + venv setup):
- `https://openclaw.example.com/` → panel login
- API key in `/opt/openclaw/.env`

### Bước 4: Hậu kiểm

```bash
ssh root@192.168.1.50 'systemctl is-active openclaw openclaw-mgmt caddy'
# Expect: active / active / active
```

---

## Approach B — Pre-install + snapshot template

Cài panel TRƯỚC khi convert template → clone xong khởi động xong ngay luôn (không chờ install).

```bash
# 1. Tạo VM thường (VMID 8000), KHÔNG template
qm create 8000 --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0 --name openclaw-bake
qm importdisk 8000 noble-server-cloudimg-amd64.img local-lvm
qm set 8000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-8000-disk-0
qm set 8000 --ide2 local-lvm:cloudinit  --boot c --bootdisk scsi0
qm set 8000 --ciuser root --ipconfig0 "ip=dhcp" --sshkeys ~/.ssh/id_rsa.pub
qm start 8000

# 2. SSH vào, chạy installer
ssh root@<DHCP-IP>
GH_TOKEN=ghp_xxx
curl -fsSL -H "Authorization: token $GH_TOKEN" -H "Accept: application/octet-stream" \
  -o /tmp/bootstrap.sh \
  "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/assets/<ID>"
GH_TOKEN=$GH_TOKEN bash /tmp/bootstrap.sh --domain CHANGEME.local --no-firewall --skip-chrome --force

# 3. Reset state (xoá .env API key + domain + machine-id) — sẽ regenerate khi clone
> /opt/openclaw/.env
> /etc/machine-id
rm -f /etc/ssh/ssh_host_*
cloud-init clean
shutdown -h now

# 4. Convert template
qm template 8000
```

Khi clone:
- VM lên với panel ĐÃ CÀI nhưng `.env` rỗng → installer chạy lại + sinh mới API key + domain.

**Nhược:** mỗi khi panel release version mới, cần re-bake template. Không tiện như Approach A.

---

## Approach C — First-boot systemd service

Nếu Proxmox không có cloud-init (lý do nào đó):

```bash
# Embed script TRONG template (Approach B preparation)
cat > /etc/systemd/system/openclaw-bootstrap.service <<'EOF'
[Unit]
Description=OpenClaw first-boot installer
ConditionPathExists=!/opt/openclaw/.first-boot-done
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/openclaw-bootstrap.sh
ExecStartPost=/usr/bin/touch /opt/openclaw/.first-boot-done

[Install]
WantedBy=multi-user.target
EOF

cat > /usr/local/bin/openclaw-bootstrap.sh <<'EOF'
#!/bin/bash
set -e
# Read params from kernel cmdline or /etc/openclaw-deploy.env
source /etc/openclaw-deploy.env  # populate DOMAIN, GH_TOKEN before snapshot
curl -fsSL -H "Authorization: token $GH_TOKEN" -H "Accept: application/octet-stream" \
  -o /tmp/bootstrap.sh \
  "https://api.github.com/repos/trungnguyen-tino/openclaw-control-panel/releases/assets/<ID>"
GH_TOKEN=$GH_TOKEN bash /tmp/bootstrap.sh --domain "$DOMAIN" --no-firewall --skip-chrome --force
EOF
chmod +x /usr/local/bin/openclaw-bootstrap.sh
systemctl enable openclaw-bootstrap
```

Lúc clone, edit `/etc/openclaw-deploy.env` rồi reboot.

---

## So sánh

| | A. Cloud-init | B. Pre-installed | C. systemd oneshot |
|---|---|---|---|
| Template build time | 1 lần | Mỗi release | 1 lần |
| Clone → ready | 3-5 min (cài) | <30s (đã sẵn) | 3-5 min |
| Update panel | Update asset ID + reclone | Re-bake template | Update asset ID + reclone |
| Customize per-VM | Cloud-init params | Cloud-init params (limited) | Edit /etc/openclaw-deploy.env |
| Standard? | ✅ Proxmox official | ❌ Hack | ⚠️ Niche |

**Recommended path:**
1. Approach A cho dev/staging (linh hoạt)
2. Approach B cho production fleet (faster boot, predictable)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Cloud-init không chạy script | Check `/var/log/cloud-init.log` + `/var/log/cloud-init-output.log` |
| `curl: (22) HTTP 401` khi tải bootstrap | GH_TOKEN sai hoặc thiếu scope `repo:read` |
| Panel không lên sau 10 min | `ssh root@<IP>`; `tail -200 /var/log/openclaw-install.log`; `systemctl status openclaw-mgmt` |
| Cert Caddy không issue | Domain chưa trỏ về IP VM; nếu LAN dùng `tls internal` (mặc định khi DOMAIN là IP) |
| `qm cloudinit dump` thấy yaml rỗng | `qm set <VMID> --cicustom user=local:snippets/X.yaml` — đúng đường dẫn snippet |

---

## Tham khảo

- Proxmox cloud-init docs: <https://pve.proxmox.com/wiki/Cloud-Init_Support>
- OpenClaw Panel install: `docs/deployment-guide.md`
- Bootstrap script: `scripts/bootstrap.sh`
