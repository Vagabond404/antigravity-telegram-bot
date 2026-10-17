#!/bin/bash
# setup_oracle.sh - Automated deployment of Antigravity Telegram Agent on Oracle Cloud / Linux VPS
# Compatible with Ubuntu 22.04/24.04 LTS, Debian, Armbian, and Oracle Linux

set -e

echo "=========================================================="
echo "⚡ Antigravity Telegram Agent — Automated Linux Deployment"
echo "=========================================================="

# 1. Verify root / sudo privileges
if [ "$EUID" -ne 0 ]; then
  if command -v sudo &>/dev/null; then
    echo "🔑 Elevating privileges via sudo..."
    exec sudo bash "$0" "$@"
  else
    echo "❌ This script must be run as root or with sudo."
    exit 1
  fi
fi

# 2. Install required system packages
echo ""
echo "📦 [1/6] Installing required system packages..."
if command -v apt-get &>/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv git curl wget ffmpeg jq ufw nodejs npm
elif command -v dnf &>/dev/null; then
    dnf install -y -q python3 python3-pip git curl wget ffmpeg jq nodejs npm
fi

# 3. Create application directory structure
echo ""
echo "📁 [2/6] Preparing application directories..."
BOT_DIR="/opt/antigravity-bot"
mkdir -p "$BOT_DIR" /root/.gemini

# 4. Install Google Antigravity CLI (agy)
echo ""
echo "🤖 [3/6] Installing Google Antigravity CLI (agy)..."
if ! command -v agy &>/dev/null && [ ! -f "/usr/local/bin/agy" ]; then
    echo "Downloading Antigravity CLI..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash || true

    # Locate the installed agy binary and link it globally
    AGY_FOUND=$(find / -name "agy" -type f -executable 2>/dev/null | grep -E "bin/agy" | head -n 1 || true)
    if [ -n "$AGY_FOUND" ]; then
        ln -sf "$AGY_FOUND" /usr/local/bin/agy
        chmod +x /usr/local/bin/agy
        echo "✅ Antigravity CLI linked to /usr/local/bin/agy"
    else
        echo "⚠️ Antigravity CLI could not be linked automatically."
        echo "   You can install it manually: curl -fsSL https://antigravity.google/cli/install.sh | bash"
    fi
else
    echo "✅ Antigravity CLI (agy) is already installed."
fi

# 5. Configure Python virtual environment
echo ""
echo "🐍 [4/6] Configuring Python virtual environment..."
cd "$BOT_DIR"

if [ ! -d "$BOT_DIR/.venv" ]; then
    python3 -m venv "$BOT_DIR/.venv"
fi

"$BOT_DIR/.venv/bin/pip" install --upgrade pip -q

if [ -f "$BOT_DIR/requirements.txt" ]; then
    echo "Installing Python dependencies from requirements.txt..."
    "$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
else
    echo "Installing core Python dependencies..."
    "$BOT_DIR/.venv/bin/pip" install python-telegram-bot httpx python-dotenv requests psutil numpy fastembed -q
fi

chmod +x "$BOT_DIR"/*.py 2>/dev/null || true

# 6. Configure systemd service
echo ""
echo "⚙️ [5/6] Configuring antigravity-bot systemd service..."
cat <<EOF > /etc/systemd/system/antigravity-bot.service
[Unit]
Description=Antigravity Telegram Agent v4.1
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/.venv/bin/python3 $BOT_DIR/bot.py
Restart=always
RestartSec=5s
Environment="PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EnvironmentFile=-/opt/antigravity-bot/.env
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

# 7. Final status check
echo ""
echo "📊 [6/6] Checking antigravity-bot service status..."
sleep 2
systemctl --no-pager status antigravity-bot.service || true

echo ""
echo "=========================================================="
echo "🎉 Antigravity Telegram Agent deployed and started!"
echo "=========================================================="
echo "ℹ️ To monitor live logs:"
echo "   journalctl -u antigravity-bot.service -f"
echo ""
echo "ℹ️ To authenticate your Google account with Antigravity CLI:"
echo "   Run: agy"
echo "=========================================================="
