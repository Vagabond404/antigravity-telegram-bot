#!/usr/bin/env bash
# ==============================================================================
# 🚀 ANTIGRAVITY TELEGRAM AGENT v4.0 — UNIVERSAL LINUX / macOS INSTALLER
# Works on Ubuntu, Debian, Armbian, Oracle Linux, Fedora, Arch, and macOS.
# ==============================================================================
set -e

BOLD="\033[1m"
CYAN="\033[96m"
GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
RESET="\033[0m"

echo -e "${CYAN}${BOLD}==================================================================${RESET}"
echo -e "${CYAN}${BOLD}   🚀 ANTIGRAVITY TELEGRAM AGENT v4.0 — ONE-COMMAND INSTALLER     ${RESET}"
echo -e "${CYAN}${BOLD}==================================================================${RESET}"

# If invoked via curl | bash outside of repository, clone or use current directory
if [ ! -f "bot.py" ]; then
    REPO_URL="${ANTIGRAVITY_BOT_REPO:-https://github.com/Vagabond404/antigravity-telegram-bot.git}"
    TARGET_DIR="${ANTIGRAVITY_BOT_DIR:-$HOME/antigravity-telegram-bot}"
    echo -e "${YELLOW}📂 Fichier bot.py non détecté dans le dossier courant.${RESET}"
    if [ -d "$TARGET_DIR" ] && [ -f "$TARGET_DIR/bot.py" ]; then
        cd "$TARGET_DIR"
    else
        echo -e "${CYAN}⬇️ Clonage du dépôt dans ${TARGET_DIR}...${RESET}"
        git clone "$REPO_URL" "$TARGET_DIR"
        cd "$TARGET_DIR"
    fi
fi

INSTALL_DIR="$(pwd)"
echo -e "${GREEN}📍 Dossier d'installation : ${INSTALL_DIR}${RESET}"

# 1. Install system dependencies (Linux apt / dnf / pacman / macOS brew)
echo -e "\n${BOLD}[1/5] Vérification des dépendances système...${RESET}"
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y -qq python3 python3-venv python3-pip curl git ffmpeg sqlite3 || true
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip curl git ffmpeg sqlite || true
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python python-pip curl git ffmpeg sqlite || true
elif command -v brew >/dev/null 2>&1; then
    brew install python git ffmpeg || true
fi

# 2. Install or Update Antigravity CLI (agy)
echo -e "\n${BOLD}[2/5] Installation / Mise à jour d'Antigravity CLI (agy)...${RESET}"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
if ! command -v agy >/dev/null 2>&1; then
    echo -e "${CYAN}⬇️ Téléchargement et installation officielle d'Antigravity CLI...${RESET}"
    curl -fsSL https://antigravity.google/cli/install.sh | bash
    export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
else
    echo -e "${GREEN}✔ Antigravity CLI déjà installé ($(command -v agy)). Vérification des mises à jour...${RESET}"
    agy update || true
fi

# Ensure ~/.local/bin is in shell profile
if ! grep -q '.local/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi

# 3. Create Python Virtual Environment & Install Packages
echo -e "\n${BOLD}[3/5] Configuration de l'environnement Python (.venv)...${RESET}"
VENV_DIR="$INSTALL_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
echo -e "${GREEN}✔ Dépendances Python installées avec succès.${RESET}"

# 4. Create start_bot.sh launcher
cat > "$INSTALL_DIR/start_bot.sh" <<EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
export PATH="\$HOME/.local/bin:/usr/local/bin:\$PATH"
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/bot.py"
EOF
chmod +x "$INSTALL_DIR/start_bot.sh"

# 5. Run Interactive Onboarding Wizard
echo -e "\n${BOLD}[4/5] Lancement de l'Assistant de Configuration...${RESET}"
"$VENV_DIR/bin/python" "$INSTALL_DIR/setup_wizard.py" < /dev/tty

# 6. Optional systemd service setup (Linux only)
if command -v systemctl >/dev/null 2>&1; then
    echo -e "\n${BOLD}[5/5] Démarrage automatique (Service Systemd 24/7)...${RESET}"
    read -r -p "  Voulez-vous installer et démarrer le service systemd en arrière-plan ? [O/n] : " INSTALL_SVC < /dev/tty
    INSTALL_SVC="${INSTALL_SVC:-o}"
    if [[ "$INSTALL_SVC" =~ ^[OoYy]$ ]]; then
        SERVICE_FILE="/etc/systemd/system/antigravity-bot.service"
        CURRENT_USER="$(whoami)"
        sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Antigravity Telegram Agent v4.0
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable antigravity-bot.service
        sudo systemctl restart antigravity-bot.service
        echo -e "${GREEN}✔ Service 'antigravity-bot' installé et démarré !${RESET}"
        echo -e "  • Voir les logs en direct : ${CYAN}sudo journalctl -u antigravity-bot -f${RESET}"
        echo -e "  • Redémarrer le bot       : ${CYAN}sudo systemctl restart antigravity-bot${RESET}"
        exit 0
    fi
fi

echo -e "\n${GREEN}${BOLD}🎉 Installation terminée !${RESET}"
read -r -p "  Voulez-vous lancer le bot maintenant ? [O/n] : " START_NOW < /dev/tty
START_NOW="${START_NOW:-o}"
if [[ "$START_NOW" =~ ^[OoYy]$ ]]; then
    exec "$INSTALL_DIR/start_bot.sh"
else
    echo -e "  Pour lancer le bot plus tard : ${CYAN}./start_bot.sh${RESET}"
fi
