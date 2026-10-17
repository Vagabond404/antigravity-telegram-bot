#!/bin/bash
# setup_autostart.sh - Configure automatic systemd startup at boot on Linux

set -e

echo "=========================================================="
echo "⚡ Antigravity Telegram Agent — Systemd Auto-Start Setup"
echo "=========================================================="

if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script as root (sudo bash setup_autostart.sh)"
  exit 1
fi

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="/usr/bin/python3"

if [ -f "$BOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$BOT_DIR/.venv/bin/python"
elif [ -f "$BOT_DIR/venv/bin/python3" ]; then
    PYTHON_BIN="$BOT_DIR/venv/bin/python3"
fi

chmod +x "$BOT_DIR"/*.py 2>/dev/null || true

cat <<EOF > /etc/systemd/system/antigravity-bot.service
[Unit]
Description=Antigravity Telegram Agent v4.1
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$PYTHON_BIN $BOT_DIR/bot.py
Restart=always
RestartSec=5s
Environment="PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EnvironmentFile=-$BOT_DIR/.env
Environment=PYTHONUNBUFFERED=1
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable antigravity-bot.service
systemctl restart antigravity-bot.service
echo "✅ Service antigravity-bot.service installed, enabled at boot, and started."
systemctl --no-pager status antigravity-bot.service || true
