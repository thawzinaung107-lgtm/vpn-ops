#!/bin/bash
# Install VPN Ops toolkit on the panel VPS (assumes PRVTPRO panel already running on :5000).
set -e
[ "$EUID" -ne 0 ] && echo "run as root" && exit 1

cp -r do-panel /opt/ && cp -r failover /opt/
chmod +x /opt/failover/*.sh /opt/failover/*.py

pip3 install --quiet --break-system-packages -r requirements.txt

# secrets — refuse defaults, prompt if missing
if ! grep -q DO_API_TOKEN /etc/environment; then
  read -p "DO API token: " DO_API_TOKEN
  read -p "Cloudflare API token: " CF_API_TOKEN
  read -p "Cloudflare zone id: " CF_ZONE_ID
  read -p "Telegram bot token: " TG_TOKEN
  read -p "Telegram chat id: " TG_CHAT
  read -p "Panel admin password: " PANEL_PASS
  cat >> /etc/environment <<EOF
DO_API_TOKEN=$DO_API_TOKEN
CF_API_TOKEN=$CF_API_TOKEN
CF_ZONE_ID=$CF_ZONE_ID
TG_TOKEN=$TG_TOKEN
TG_CHAT=$TG_CHAT
PANEL_PASS=$PANEL_PASS
EOF
  chmod 600 /etc/environment
fi

cat > /etc/systemd/system/do-panel.service <<'EOF'
[Unit]
Description=DO Control panel module
After=network.target docker.service
[Service]
WorkingDirectory=/opt/do-panel
ExecStart=/usr/local/bin/uvicorn app:app --host 127.0.0.1 --port 8787
Restart=always
EnvironmentFile=/etc/environment
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now do-panel

# monitor + backup crons
cat > /etc/cron.d/vpn-monitor <<'EOF'
*/2 * * * * root . /etc/environment && /usr/bin/python3 /opt/failover/monitor.py >> /var/log/vpn-monitor.log 2>&1
0 9 * * * root . /etc/environment && /usr/bin/python3 /opt/failover/monitor.py digest >> /var/log/vpn-monitor.log 2>&1
EOF
cat > /etc/cron.d/vpn-backup <<'EOF'
0 3 * * * root NODE_PASSWORD="${NODE_PASSWORD:-Amnezia@123456Amnezia}" /opt/failover/backup_nodes.sh >> /var/log/vpn-backup.log 2>&1
EOF
systemctl restart cron
echo "installed. add Caddy route: handle /do* { reverse_proxy 127.0.0.1:8787 }"
