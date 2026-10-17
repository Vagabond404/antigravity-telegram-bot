#!/usr/bin/env python3
"""
Antigravity Telegram Agent — Interactive Onboarding & Setup Wizard
Cross-Platform (Windows, Linux, macOS)
"""
import os
import sys
import json
import time
import shutil
import platform
import subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
SETTINGS_FILE = BASE_DIR / "settings.json"
USERS_FILE = BASE_DIR / "users.json"

IS_WINDOWS = platform.system().lower() == "windows"

# ANSI colors (enabled on modern Windows 10/11 & Unix)
if IS_WINDOWS:
    os.system("")  # Enable VT100 escape sequences on Windows console

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def banner():
    print(f"\n{CYAN}{BOLD}=================================================================={RESET}")
    print(f"{CYAN}{BOLD}   🚀 ANTIGRAVITY TELEGRAM AGENT v4.0 — ASSISTANT D'INSTALLATION   {RESET}")
    print(f"{CYAN}{BOLD}=================================================================={RESET}\n")


def find_agy() -> str:
    """Locate the Antigravity CLI binary on Windows, Linux, or macOS."""
    from config import find_agy_binary
    return find_agy_binary()


def install_or_update_agy() -> str:
    """Ensure Antigravity CLI (agy) is installed and up to date."""
    print(f"{BOLD}[1/4] Vérification d'Antigravity CLI (agy)...{RESET}")
    agy_bin = find_agy()
    exists = shutil.which(agy_bin) or Path(agy_bin).exists()

    if exists:
        try:
            res = subprocess.run([agy_bin, "--version"], capture_output=True, text=True, timeout=10)
            ver = (res.stdout or res.stderr).strip()
            print(f"  {GREEN}✔ Antigravity CLI détecté :{RESET} {ver} ({agy_bin})")
            ans = input(f"  Voulez-vous vérifier les mises à jour d'Antigravity CLI ? [O/n] : ").strip().lower()
            if ans in ("", "o", "oui", "y", "yes"):
                print("  ⏳ Mise à jour d'Antigravity CLI (`agy update`)...")
                subprocess.run([agy_bin, "update"], timeout=120)
            return agy_bin
        except Exception as e:
            print(f"  {YELLOW}⚠ Erreur lors de l'exécution de {agy_bin}: {e}{RESET}")

    print(f"  {YELLOW}⚡ Antigravity CLI n'est pas encore installé. Installation automatique...{RESET}")
    try:
        if IS_WINDOWS:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                   "irm https://antigravity.google/cli/install.ps1 | iex"]
            subprocess.run(cmd, check=True)
        else:
            cmd = ["bash", "-c", "curl -fsSL https://antigravity.google/cli/install.sh | bash"]
            subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"  {RED}❌ Échec de l'installation automatique d'Antigravity CLI : {e}{RESET}")
        print(f"  Vous pouvez l'installer manuellement depuis : https://antigravity.google/cli")

    agy_bin = find_agy()
    if shutil.which(agy_bin) or Path(agy_bin).exists():
        print(f"  {GREEN}✔ Antigravity CLI installé avec succès : {agy_bin}{RESET}")
    else:
        print(f"  {YELLOW}⚠ Binaire `agy` non trouvé dans le PATH standard. Assurez-vous qu'il est installé.{RESET}")
    return agy_bin


def check_agy_auth(agy_bin: str) -> list:
    """Verify that Antigravity CLI can list models and is authenticated."""
    print(f"\n{BOLD}[2/4] Connexion & Authentification Antigravity CLI...{RESET}")
    models = []
    if not (shutil.which(agy_bin) or Path(agy_bin).exists()):
        print(f"  {YELLOW}⚠ Antigravity CLI introuvable, étape d'authentification ignorée.{RESET}")
        return models

    def _try_list_models():
        try:
            res = subprocess.run([agy_bin, "models"], capture_output=True, text=True, timeout=20)
            out = (res.stdout or "").strip()
            parsed = []
            for line in out.splitlines():
                if "\t" in line:
                    mid, mname = line.split("\t", 1)
                    parsed.append((mid.strip(), mname.strip()))
            return parsed, out + "\n" + (res.stderr or "")
        except Exception as exc:
            return [], str(exc)

    models, raw_out = _try_list_models()
    if models:
        print(f"  {GREEN}✔ Authentifié à Antigravity CLI ({len(models)} modèles disponibles) !{RESET}")
        for mid, mname in models[:6]:
            print(f"    • {mname} ({mid})")
        return models

    print(f"  {YELLOW}⚠ Antigravity CLI nécessite une connexion ou une authentification.{RESET}")
    print(f"  Nous allons lancer `{agy_bin}` pour vous permettre de vous connecter.")
    print(f"  {CYAN}Astuce :{RESET} Une fois connecté dans l'interface Antigravity CLI, tapez `/exit` ou `Ctrl+C` pour revenir à cet assistant.\n")
    ans = input("  Appuyez sur [Entrée] pour lancer la connexion Antigravity CLI (ou 's' pour passer) : ").strip().lower()
    if ans != "s":
        try:
            subprocess.run([agy_bin, "-p", "Say OK if connected", "--max-turns", "1"])
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"  {YELLOW}Note : {e}{RESET}")
        models, _ = _try_list_models()
        if models:
            print(f"  {GREEN}✔ Connexion Antigravity CLI confirmée ({len(models)} modèles disponibles) !{RESET}")

    return models


def validate_telegram_token(token: str) -> dict | None:
    """Validate Telegram Bot Token via getMe API."""
    if not token or ":" not in token:
        return None
    if not requests:
        return {"username": "bot", "first_name": "Telegram Bot"}
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = r.json()
        if data.get("ok"):
            return data.get("result", {})
    except Exception:
        pass
    return None


def poll_admin_from_telegram(token: str, bot_username: str) -> tuple[int | None, str | None]:
    """Wait for the user to send /start to their bot and grab their user ID."""
    if not requests:
        return None, None
    print(f"\n  📲 Ouvrez Telegram et envoyez {BOLD}/start{RESET} à {CYAN}@{bot_username}{RESET} maintenant !")
    print("  ⏳ En attente de votre message sur Telegram (60s max, Ctrl+C pour entrer l'ID manuellement)...")
    offset = None
    try:
        # Flush old updates first
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout": 1}, timeout=5).json()
        if r.get("ok") and r.get("result"):
            offset = r["result"][-1]["update_id"] + 1
    except Exception:
        pass

    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            params = {"timeout": 5}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params=params, timeout=10).json()
            if r.get("ok"):
                for upd in r.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or upd.get("edited_message")
                    if msg and "from" in msg:
                        user = msg["from"]
                        uid = user.get("id")
                        uname = user.get("username") or user.get("first_name") or "Admin"
                        # Send confirmation message
                        try:
                            requests.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={
                                    "chat_id": uid,
                                    "text": f"✅ *Connexion Administrateur Réussie !*\n\nBonjour *{uname}* (`{uid}`), votre bot Antigravity v4.0 est maintenant lié à votre compte.",
                                    "parse_mode": "Markdown",
                                },
                                timeout=5,
                            )
                        except Exception:
                            pass
                        return uid, uname
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  ⏹ Détection automatique interrompue.")
    except Exception as e:
        print(f"\n  {YELLOW}⚠ Erreur lors de la détection automatique : {e}{RESET}")
    return None, None


def configure_telegram_and_admin() -> tuple[str, int | None, str]:
    """Prompt for Telegram token and Admin ID."""
    print(f"\n{BOLD}[3/4] Configuration du Bot Telegram...{RESET}")
    existing_token = ""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and val != "your_telegram_bot_token_here":
                    existing_token = val

    bot_info = None
    token = existing_token
    if existing_token:
        masked = existing_token[:8] + "..." + existing_token[-5:]
        ans = input(f"  Token actuel détecté ({masked}). Le conserver ? [O/n] : ").strip().lower()
        if ans not in ("", "o", "oui", "y", "yes"):
            token = ""
        else:
            bot_info = validate_telegram_token(token)

    while not bot_info:
        print(f"  💡 Créez un bot ou récupérez votre token auprès de {CYAN}@BotFather{RESET} sur Telegram.")
        token = input(f"  🔑 Entrez votre {BOLD}TELEGRAM_BOT_TOKEN{RESET} : ").strip().strip('"').strip("'")
        bot_info = validate_telegram_token(token)
        if bot_info:
            print(f"  {GREEN}✔ Token valide ! Bot connecté : {bot_info.get('first_name')} (@{bot_info.get('username')}){RESET}")
        else:
            print(f"  {RED}❌ Token invalide ou impossible de joindre l'API Telegram. Réessayez.{RESET}")

    bot_username = bot_info.get("username", "votre_bot")

    print(f"\n{BOLD}[4/4] Configuration du Compte Administrateur...{RESET}")
    print("  Comment souhaitez-vous configurer votre compte Administrateur Telegram ?")
    print(f"    {BOLD}1{RESET}) Détection automatique en envoyant `/start` à @{bot_username} maintenant (Recommandé)")
    print(f"    {BOLD}2{RESET}) Entrer mon Telegram User ID manuellement")
    print(f"    {BOLD}3{RESET}) Automatique au premier `/start` après le lancement du bot")
    choice = input("  Votre choix [1/2/3] (défaut: 1) : ").strip() or "1"

    admin_id = None
    admin_name = "Admin"

    if choice == "1":
        admin_id, detected_name = poll_admin_from_telegram(token, bot_username)
        if admin_id:
            admin_name = detected_name or "Admin"
            print(f"  {GREEN}✔ Administrateur détecté automatiquement : {admin_name} (ID: {admin_id}){RESET}")
        else:
            print(f"  {YELLOW}⚠ Aucun message reçu. Le premier utilisateur qui enverra `/start` deviendra Administrateur.{RESET}")
    elif choice == "2":
        raw_id = input("  🆔 Entrez votre Telegram User ID (ex: 123456789) : ").strip()
        if raw_id.isdigit():
            admin_id = int(raw_id)
            admin_name = input("  👤 Votre nom/pseudo Administrateur (défaut: Admin) : ").strip() or "Admin"
            print(f"  {GREEN}✔ Administrateur configuré : {admin_name} (ID: {admin_id}){RESET}")
        else:
            print(f"  {YELLOW}⚠ ID non numérique. Le premier utilisateur qui enverra `/start` deviendra Administrateur.{RESET}")
    else:
        print(f"  {GREEN}✔ Mode Auto-Claim activé : le premier utilisateur qui enverra `/start` à @{bot_username} sera Administrateur.{RESET}")

    return token, admin_id, admin_name


def save_configuration(agy_bin: str, token: str, admin_id: int | None, admin_name: str, models: list):
    """Write .env, settings.json, and users.json safely."""
    from config import DEFAULT_SETTINGS
    env_lines = [
        "# Antigravity Telegram Agent v4.0 Configuration",
        f"TELEGRAM_BOT_TOKEN={token}",
        f"ALLOWED_USER_ID={admin_id if admin_id else ''}",
        f"AGY_BIN_PATH={agy_bin or ''}",
        f"WORKSPACE_DIR={BASE_DIR}",
    ]
    ENV_FILE.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    if not IS_WINDOWS:
        try:
            os.chmod(ENV_FILE, 0o600)
        except Exception:
            pass

    default_model = "gemini-4-argon-medium"
    if models:
        model_ids = [m[0] for m in models]
        if default_model not in model_ids:
            default_model = model_ids[0]

    settings = DEFAULT_SETTINGS.copy()
    settings["model"] = default_model
    settings["workspace_dir"] = str(BASE_DIR)

    if SETTINGS_FILE.exists():
        try:
            existing = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            settings.update(existing)
            settings["workspace_dir"] = str(BASE_DIR)
            if not settings.get("model"):
                settings["model"] = default_model
        except Exception:
            pass
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")

    users_data = {}
    if USERS_FILE.exists():
        try:
            loaded = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "admins" not in loaded:
                users_data = loaded
        except Exception:
            pass
    if admin_id:
        today = time.strftime("%Y-%m-%d")
        users_data[str(admin_id)] = {
            "name": admin_name,
            "username": "",
            "role": "admin",
            "auto_approve": True,
            "daily_download_limit": 0,
            "downloads_today": 0,
            "last_download_date": today,
            "created_at": today,
        }
    USERS_FILE.write_text(json.dumps(users_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{GREEN}{BOLD}=================================================================={RESET}")
    print(f"{GREEN}{BOLD}   ✅ CONFIGURATION TERMINÉE AVEC SUCCÈS !                        {RESET}")
    print(f"{GREEN}{BOLD}=================================================================={RESET}")
    print(f"  • Fichier {BOLD}.env{RESET} généré")
    print(f"  • Fichier {BOLD}settings.json{RESET} initialisé (Modèle: {settings.get('model')})")
    print(f"  • Fichier {BOLD}users.json{RESET} prêt")
    print(f"\n  🚀 Vous pouvez gérer {BOLD}tous les paramètres{RESET} directement depuis Telegram avec {CYAN}/settings{RESET} !\n")


def run_wizard():
    banner()
    agy_bin = install_or_update_agy()
    models = check_agy_auth(agy_bin)
    token, admin_id, admin_name = configure_telegram_and_admin()
    save_configuration(agy_bin, token, admin_id, admin_name, models)


if __name__ == "__main__":
    try:
        run_wizard()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Configuration interrompue par l'utilisateur.{RESET}")
        sys.exit(1)
