#!/usr/bin/env bash
# Provision the LedgerHouse production host on Hetzner Cloud.
#
# Prerequisites:
#   1. Hetzner Cloud account + project (console.hetzner.cloud)
#   2. API token with Read & Write:  Project -> Security -> API tokens
#   3. export HCLOUD_TOKEN=...   (never commit this)
#
# Usage:  bash deploy/hetzner/provision.sh
#
# Cost note: CX32 is ~EUR 7.60/month (billed hourly), plus ~20% if
# ENABLE_BACKUPS=1 (default) for Hetzner's 7-day rolling snapshots.

set -euo pipefail

SERVER_NAME="${SERVER_NAME:-ledgerhouse-prod}"
SERVER_TYPE="${SERVER_TYPE:-cx32}"          # 4 vCPU / 8 GB / 80 GB
IMAGE="${IMAGE:-ubuntu-24.04}"
LOCATION="${LOCATION:-fsn1}"                # fsn1 Falkenstein | nbg1 Nuremberg | hel1 Helsinki
SSH_KEY_NAME="${SSH_KEY_NAME:-kfrem-workstation}"
SSH_PUB_KEY_FILE="${SSH_PUB_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
FIREWALL_NAME="${FIREWALL_NAME:-web-basic}"
ENABLE_BACKUPS="${ENABLE_BACKUPS:-1}"
CLOUD_INIT="$(dirname "$0")/cloud-init.yaml"

HCLOUD="${HCLOUD:-hcloud}"
command -v "$HCLOUD" >/dev/null 2>&1 || HCLOUD="$HOME/bin/hcloud.exe"

if [ -z "${HCLOUD_TOKEN:-}" ]; then
    echo "ERROR: HCLOUD_TOKEN is not set. Create a Read/Write API token in the"
    echo "Hetzner Cloud console (Project -> Security -> API tokens) and run:"
    echo "  export HCLOUD_TOKEN=<token>"
    exit 1
fi

echo "==> Uploading SSH key '$SSH_KEY_NAME' (if not present)"
if ! "$HCLOUD" ssh-key describe "$SSH_KEY_NAME" >/dev/null 2>&1; then
    "$HCLOUD" ssh-key create --name "$SSH_KEY_NAME" --public-key-from-file "$SSH_PUB_KEY_FILE"
else
    echo "    already exists"
fi

echo "==> Creating firewall '$FIREWALL_NAME' (if not present)"
if ! "$HCLOUD" firewall describe "$FIREWALL_NAME" >/dev/null 2>&1; then
    "$HCLOUD" firewall create --name "$FIREWALL_NAME"
    "$HCLOUD" firewall add-rule "$FIREWALL_NAME" --direction in --protocol tcp --port 22  --source-ips 0.0.0.0/0 --source-ips ::/0 --description "SSH"
    "$HCLOUD" firewall add-rule "$FIREWALL_NAME" --direction in --protocol tcp --port 80  --source-ips 0.0.0.0/0 --source-ips ::/0 --description "HTTP"
    "$HCLOUD" firewall add-rule "$FIREWALL_NAME" --direction in --protocol tcp --port 443 --source-ips 0.0.0.0/0 --source-ips ::/0 --description "HTTPS"
    "$HCLOUD" firewall add-rule "$FIREWALL_NAME" --direction in --protocol icmp --source-ips 0.0.0.0/0 --source-ips ::/0 --description "ping"
else
    echo "    already exists"
fi

if "$HCLOUD" server describe "$SERVER_NAME" >/dev/null 2>&1; then
    echo "==> Server '$SERVER_NAME' already exists — not recreating."
else
    echo "==> Creating $SERVER_TYPE server '$SERVER_NAME' in $LOCATION"
    "$HCLOUD" server create \
        --name "$SERVER_NAME" \
        --type "$SERVER_TYPE" \
        --image "$IMAGE" \
        --location "$LOCATION" \
        --ssh-key "$SSH_KEY_NAME" \
        --firewall "$FIREWALL_NAME" \
        --user-data-from-file "$CLOUD_INIT"
fi

if [ "$ENABLE_BACKUPS" = "1" ]; then
    echo "==> Enabling automatic backups (+20% of server price)"
    "$HCLOUD" server enable-backup "$SERVER_NAME" || true
fi

IP="$("$HCLOUD" server ip "$SERVER_NAME")"
echo
echo "============================================================"
echo " Server ready: $SERVER_NAME ($SERVER_TYPE, $LOCATION)"
echo " IPv4: $IP"
echo "============================================================"
echo
echo "Next steps:"
echo "  1. DNS: create A records pointing your app domains at $IP"
echo "  2. Wait ~3-4 min for cloud-init to finish, then:"
echo "       ssh root@$IP 'cloud-init status --wait && docker --version && caddy version'"
echo "  3. Deploy LedgerHouse:"
echo "       ssh root@$IP 'git clone https://github.com/kfrem/ledgerhouse /srv/ledgerhouse'"
echo "       (copy .env with real secrets to /srv/ledgerhouse/.env, then"
echo "        docker compose -f docker-compose.prod.yml up -d --build)"
echo "  4. Edit /etc/caddy/Caddyfile with the real domains and: systemctl reload caddy"
