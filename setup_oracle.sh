#!/bin/bash
# setup_oracle.sh - Déploiement automatisé de l'Agent Magma sur Oracle Cloud Free Tier
# Compatible Ubuntu 22.04/24.04 LTS et Oracle Linux / Debian

set -e

echo "=========================================================="
echo "⚡ Installation & Déploiement Agent IA Magma sur Oracle Cloud"
echo "=========================================================="

# 1. Vérification des privilèges root / sudo
if [ "$EUID" -ne 0 ]; then
  if command -v sudo &>/dev/null; then
    echo "🔑 Élévation des privilèges via sudo..."
    exec sudo bash "$0" "$@"
  else
    echo "❌ Ce script doit être exécuté en root ou avec sudo."
    exit 1
  fi
fi

# 2. Mise à jour et paquets système requis
echo ""
echo "📦 [1/6] Installation des paquets système..."
if command -v apt-get &>/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv git curl wget ffmpeg jq ufw
elif command -v dnf &>/dev/null; then
    dnf install -y -q python3 python3-pip git curl wget ffmpeg jq
fi

# 3. Création de l'arborescence
echo ""
echo "📁 [2/6] Préparation des répertoires applicatifs..."
BOT_DIR="/opt/antigravity-bot"
mkdir -p "$BOT_DIR" /root/.gemini

# 4. Installation d'Antigravity CLI (agy)
echo ""
echo "🤖 [3/6] Installation de Google Antigravity CLI (agy)..."
if ! command -v agy &>/dev/null && [ ! -f "/usr/local/bin/agy" ]; then
    echo "Téléchargement d'Antigravity CLI..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash || true
    
    # Trouver l'exécutable agy installé
    AGY_FOUND=$(find / -name "agy" -type f -executable 2>/dev/null | grep -E "bin/agy" | head -n 1 || true)
    if [ -n "$AGY_FOUND" ]; then
        ln -sf "$AGY_FOUND" /usr/local/bin/agy
        chmod +x /usr/local/bin/agy
        echo "✅ Antigravity CLI lié avec succès à /usr/local/bin/agy"
    else
        echo "⚠️ Antigravity CLI n'a pas pu être installé automatiquement via le script."
        echo "   Vous pourrez exécuter : curl -fsSL https://antigravity.google/cli/install.sh | bash"
    fi
else
    echo "✅ Antigravity CLI (agy) est déjà présent."
fi

# 5. Configuration de l'environnement virtuel Python
echo ""
echo "🐍 [4/6] Configuration de l'environnement virtuel Python..."
cd "$BOT_DIR"

if [ ! -d "$BOT_DIR/venv" ]; then
    python3 -m venv "$BOT_DIR/venv"
fi

"$BOT_DIR/venv/bin/pip" install --upgrade pip -q

if [ -f "$BOT_DIR/requirements.txt" ]; then
    echo "Installation des dépendances Python (python-telegram-bot, httpx, etc.)..."
    "$BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
else
    echo "Installation directe des dépendances principales..."
    "$BOT_DIR/venv/bin/pip" install python-telegram-bot httpx python-dotenv requests psutil numpy fastembed -q
fi

# Rendre exécutables tous les scripts Python
chmod +x "$BOT_DIR"/*.py 2>/dev/null || true

# 6. Service systemd
echo ""
echo "⚙️ [5/6] Configuration du service systemd antigravity-bot..."
cat <<EOF > /etc/systemd/system/antigravity-bot.service
[Unit]
Description=Antigravity Telegram Bot Interactive Bridge (Oracle Cloud)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python3 $BOT_DIR/bot.py
Restart=always
RestartSec=5s
Environment="PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EnvironmentFile=/opt/antigravity-bot/.env
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

# 7. Vérification finale
echo ""
echo "📊 [6/6] Vérification du service antigravity-bot..."
sleep 2
systemctl --no-pager status antigravity-bot.service || true

echo ""
echo "=========================================================="
echo "🎉 Agent IA Magma déployé et activé avec succès !"
echo "=========================================================="
echo "ℹ️ Pour surveiller les logs en temps réel :"
echo "   journalctl -u antigravity-bot.service -f"
echo ""
echo "ℹ️ Pour connecter votre compte Google à l'Antigravity CLI (première connexion) :"
echo "   Lancez simplement : agy"
echo "   Et ouvrez l'URL Google affichée pour autoriser l'agent avec votre compte Google habituel."
echo "=========================================================="
