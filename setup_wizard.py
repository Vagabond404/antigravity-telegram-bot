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
from typing import List

import config
from config import find_agy_binary, BASE_DIR, ENV_FILE, SETTINGS_FILE, IS_WINDOWS

try:
    import requests
except ImportError:
    requests = None

USERS_FILE = BASE_DIR / "users.json"

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
    return find_agy_binary() or ("agy.exe" if IS_WINDOWS else "agy")


def _ensure_unix_global_symlink(agy_bin: str) -> None:
    """Ensure /usr/local/bin/agy points to agy_bin on Linux/macOS so 'agy' works in any shell."""
    if IS_WINDOWS or not agy_bin:
        return
    p = Path(agy_bin)
    if not p.is_file():
        return
    target = Path("/usr/local/bin/agy")
    try:
        if not target.exists() or target.resolve() != p.resolve():
            if os.access("/usr/local/bin", os.W_OK):
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(p)
            else:
                subprocess.run(["sudo", "ln", "-sf", str(p), str(target)], capture_output=True, timeout=5)
    except Exception:
        pass


def install_or_update_agy() -> str:
    """Ensure Antigravity CLI (agy) is installed and up to date."""
    print(f"{BOLD}[1/5] Vérification d'Antigravity CLI (agy)...{RESET}")
    agy_bin = find_agy()
    exists = shutil.which(agy_bin) or Path(agy_bin).exists()

    if exists:
        _ensure_unix_global_symlink(agy_bin)
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
        _ensure_unix_global_symlink(agy_bin)
        print(f"  {GREEN}✔ Antigravity CLI installé avec succès : {agy_bin}{RESET}")
    else:
        print(f"  {YELLOW}⚠ Binaire `agy` non trouvé dans le PATH standard. Assurez-vous qu'il est installé.{RESET}")
    return agy_bin


def check_agy_auth(agy_bin: str) -> list:
    """Verify that Antigravity CLI can list models and is authenticated."""
    print(f"\n{BOLD}[2/5] Connexion & Authentification Antigravity CLI...{RESET}")
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

    print(f"  {YELLOW}⚠ Antigravity CLI nécessite une connexion à votre compte Google.{RESET}")
    print(f"  Nous allons lancer `{agy_bin}` en mode interactif pour afficher le lien de connexion Google.")
    print(f"  {CYAN}Instructions :{RESET}")
    print(f"    1. Ouvrez l'URL Google affichée dans votre navigateur et connectez-vous.")
    print(f"    2. Dès que l'interface Antigravity CLI est connectée, tapez {BOLD}/exit{RESET} (ou {BOLD}Ctrl+C{RESET}) pour revenir ici !\n")
    ans = input("  Appuyez sur [Entrée] pour lancer la connexion Antigravity CLI (ou 's' pour passer) : ").strip().lower()
    if ans != "s":
        try:
            # Launch interactive `agy` without unsupported flags so Google OAuth flow works natively
            subprocess.run([agy_bin])
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"  {YELLOW}Note : {e}{RESET}")
        models, _ = _try_list_models()
        if models:
            print(f"\n  {GREEN}✔ Connexion Antigravity CLI confirmée ({len(models)} modèles disponibles) !{RESET}")
        else:
            print(f"\n  {YELLOW}ℹ Vous pourrez vous connecter à tout moment en tapant : {BOLD}agy{RESET}")

    return models


def validate_telegram_token(token: str) -> dict | None:
    """Validate Telegram Bot Token via getMe API."""
    if not token or ":" not in token:
        return None
    if not requests:
        return {"username": "bot", "first_name": "Telegram Bot"}
    for attempt in range(3):
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            data = r.json()
            if data.get("ok"):
                return data.get("result", {})
        except Exception:
            time.sleep(1)
    return None


def poll_admin_from_telegram(token: str, bot_username: str) -> tuple[int | None, str | None]:
    """Wait for the user to send /start to their bot and grab their user ID."""
    if not requests:
        return None, None
    print(f"\n  📲 Ouvrez Telegram et envoyez {BOLD}/start{RESET} à {CYAN}@{bot_username}{RESET} maintenant !")
    print("  ⏳ En attente de votre message sur Telegram (60s max, Ctrl+C pour passer)...")
    offset = None
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout": 1}, timeout=6).json()
        if r.get("ok") and r.get("result"):
            offset = r["result"][-1]["update_id"] + 1
    except Exception:
        pass

    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            try:
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
                            try:
                                requests.post(
                                    f"https://api.telegram.org/bot{token}/sendMessage",
                                    json={
                                        "chat_id": uid,
                                        "text": f"✅ *Connexion Administrateur Réussie !*\n\nBonjour *{uname}* (`{uid}`), votre bot Antigravity v4.0 est maintenant lié à votre compte.",
                                        "parse_mode": "Markdown",
                                    },
                                    timeout=6,
                                )
                            except Exception:
                                pass
                            return uid, uname
            except KeyboardInterrupt:
                raise
            except Exception:
                time.sleep(2)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  ⏹ Détection automatique interrompue.")
    return None, None


def configure_telegram_and_admin() -> tuple[str, int | None, str]:
    """Prompt for Telegram token and Admin ID."""
    print(f"\n{BOLD}[3/5] Configuration du Bot Telegram...{RESET}")
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

    print(f"\n{BOLD}[4/5] Configuration du Compte Administrateur...{RESET}")
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


def _ensure_nodejs_available() -> bool:
    """Ensure Node.js / npx is installed so MCP servers can run."""
    if shutil.which("npx") or shutil.which("npx.cmd"):
        return True
    print(f"  {YELLOW}⚡ Node.js (`npx`) est requis pour exécuter les serveurs MCP. Installation automatique...{RESET}")
    try:
        if IS_WINDOWS:
            if shutil.which("winget"):
                subprocess.run(
                    ["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements", "--accept-source-agreements"],
                    timeout=180,
                )
        else:
            if shutil.which("apt-get"):
                subprocess.run(["bash", "-c", "sudo apt-get update -qq && sudo apt-get install -y -qq nodejs npm || apt-get install -y -qq nodejs npm"], timeout=180)
            elif shutil.which("dnf"):
                subprocess.run(["bash", "-c", "sudo dnf install -y nodejs npm || dnf install -y nodejs npm"], timeout=180)
            elif shutil.which("pacman"):
                subprocess.run(["bash", "-c", "sudo pacman -Sy --noconfirm nodejs npm || pacman -Sy --noconfirm nodejs npm"], timeout=180)
    except Exception as e:
        print(f"  {YELLOW}⚠ Impossible d'installer automatiquement Node.js : {e}{RESET}")
    return bool(shutil.which("npx") or shutil.which("npx.cmd"))


def configure_mcp_and_skills(agy_bin: str) -> List[str]:
    """Install the built-in Telegram Bot Mastery skill and offer recommended MCP servers."""
    print(f"\n{BOLD}[5/5] Skill IA par défaut & Serveurs MCP Recommandés...{RESET}")

    # 1. Install the built-in telegram-bot-mastery skill
    skill_path = config.ensure_default_skill_installed()
    if skill_path:
        print(f"  {GREEN}✔ Skill par défaut installé :{RESET} {BOLD}telegram-bot-mastery{RESET}")
        print(f"    (Permet à l'IA de maîtriser toutes les fonctions du bot Telegram, l'envoi de médias, la mémoire Mem0, etc.)")

    # 2. Propose Recommended MCP Servers (Playwright, Firecrawl, Docker, Context7, Sequential Thinking, GitHub)
    catalog = config.RECOMMENDED_MCP_SERVERS
    print(f"\n  {CYAN}{BOLD}🔌 Catalogue des Serveurs MCP Recommandés :{RESET}")
    default_nums = []
    for idx, srv in enumerate(catalog, start=1):
        star = f"{GREEN}[Recommandé]{RESET}" if srv.get("default_selected") else f"{YELLOW}[Optionnel]{RESET}"
        if srv.get("default_selected"):
            default_nums.append(str(idx))
        print(f"    {BOLD}{idx}{RESET}) {BOLD}{srv['title']}{RESET} {star}")
        print(f"       └ {srv['description']}")

    default_str = ",".join(default_nums)
    print(f"\n  💡 Entrez les numéros à installer séparés par des virgules (ex: {BOLD}1,2,3{RESET}),")
    print(f"     appuyez sur {BOLD}[Entrée]{RESET} pour installer la sélection recommandée ({BOLD}{default_str}{RESET}), ou tapez {BOLD}n{RESET} pour passer.")
    raw_sel = input(f"  Votre choix [{default_str} / all / n] : ").strip().lower()

    if raw_sel in ("n", "non", "no", "s", "skip", "0"):
        print(f"  {YELLOW}ℹ Installation MCP ignorée (vous pourrez les installer en 1 clic sur Telegram via /mcp).{RESET}")
        return []

    selected_indices: List[int] = []
    if raw_sel in ("", "o", "oui", "y", "yes"):
        selected_indices = [int(x) for x in default_nums]
    elif raw_sel in ("a", "all", "tous", "tout"):
        selected_indices = list(range(1, len(catalog) + 1))
    else:
        for part in raw_sel.replace(" ", ",").split(","):
            if part.strip().isdigit():
                val = int(part.strip())
                if 1 <= val <= len(catalog) and val not in selected_indices:
                    selected_indices.append(val)

    if not selected_indices:
        return []

    _ensure_nodejs_available()
    npx_cmd = "npx.cmd" if (IS_WINDOWS and shutil.which("npx.cmd")) else "npx"

    installed_mcp: List[str] = []
    for idx in selected_indices:
        srv = catalog[idx - 1]
        srv_id = srv["id"]
        env_key = srv.get("env_key")
        env_val = ""
        if env_key:
            env_val = os.getenv(env_key, "").strip()
            if not env_val:
                prompt_txt = srv.get("env_prompt") or f"Clé {env_key} (Entrée pour passer)"
                env_val = input(f"  🔑 [{srv_id}] {prompt_txt} : ").strip()
                if env_val:
                    config.update_env_var(env_key, env_val)

        cmd = [agy_bin, "mcp", "add"]
        if env_key and env_val:
            cmd.extend(["--env", f"{env_key}={env_val}"])
        cmd.extend([srv_id, "--", npx_cmd] + list(srv["args"]))

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                print(f"  {GREEN}✔ Serveur MCP '{srv_id}' configuré avec succès !{RESET}")
                installed_mcp.append(srv_id)
            else:
                err_txt = (res.stderr or res.stdout or "").strip()
                print(f"  {YELLOW}⚠ Avertissement MCP '{srv_id}' : {err_txt}{RESET}")
        except Exception as e:
            print(f"  {YELLOW}⚠ Impossible d'ajouter le serveur MCP '{srv_id}' : {e}{RESET}")

    return installed_mcp


def save_configuration(agy_bin: str, token: str, admin_id: int | None, admin_name: str, models: list, installed_mcp: List[str] | None = None):
    """Write .env, settings.json, and users.json safely."""
    from config import DEFAULT_SETTINGS
    # Preserve any API keys (e.g. FIRECRAWL_API_KEY) already written to .env
    extra_env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                if k not in ("TELEGRAM_BOT_TOKEN", "ALLOWED_USER_ID", "AGY_BIN_PATH", "WORKSPACE_DIR"):
                    extra_env[k] = v.strip()

    env_lines = [
        "# Antigravity Telegram Agent v4.0 Configuration",
        f"TELEGRAM_BOT_TOKEN={token}",
        f"ALLOWED_USER_ID={admin_id if admin_id else ''}",
        f"AGY_BIN_PATH={agy_bin or ''}",
        f"WORKSPACE_DIR={BASE_DIR}",
    ]
    for k, v in extra_env.items():
        env_lines.append(f"{k}={v}")

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
    print(f"  • Skill IA {BOLD}telegram-bot-mastery{RESET} activé")
    if installed_mcp:
        print(f"  • Serveurs MCP configurés : {BOLD}{', '.join(installed_mcp)}{RESET}")
    print(f"\n  🚀 Vous pouvez gérer {BOLD}tous les paramètres et serveurs MCP{RESET} depuis Telegram avec {CYAN}/settings{RESET} et {CYAN}/mcp{RESET} !\n")


def run_wizard():
    banner()
    agy_bin = install_or_update_agy()
    models = check_agy_auth(agy_bin)
    token, admin_id, admin_name = configure_telegram_and_admin()
    installed_mcp = configure_mcp_and_skills(agy_bin)
    save_configuration(agy_bin, token, admin_id, admin_name, models, installed_mcp)


if __name__ == "__main__":
    try:
        run_wizard()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Configuration interrompue par l'utilisateur.{RESET}")
        sys.exit(1)
