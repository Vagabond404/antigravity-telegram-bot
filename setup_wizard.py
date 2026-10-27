#!/usr/bin/env python3
"""
Antigravity Telegram Agent — Interactive Onboarding & Setup Wizard
Cross-Platform (Windows, Linux, macOS)
English default with multi-language and multi-account tier support.
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
    print(f"{CYAN}{BOLD}   🚀 ANTIGRAVITY TELEGRAM AGENT v4.2 — SETUP WIZARD             {RESET}")
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
    print(f"{BOLD}[1/5] Checking Antigravity CLI (agy)...{RESET}")
    agy_bin = find_agy()
    exists = shutil.which(agy_bin) or Path(agy_bin).exists()

    if exists:
        _ensure_unix_global_symlink(agy_bin)
        try:
            res = subprocess.run([agy_bin, "--version"], capture_output=True, text=True, timeout=10)
            ver = (res.stdout or res.stderr).strip()
            print(f"  {GREEN}✔ Antigravity CLI detected:{RESET} {ver} ({agy_bin})")
            ans = input(f"  Would you like to check for Antigravity CLI updates? [Y/n]: ").strip().lower()
            if ans in ("", "y", "yes", "o", "oui"):
                print("  ⏳ Updating Antigravity CLI (`agy update`)...")
                subprocess.run([agy_bin, "update"], timeout=120)
            return agy_bin
        except Exception as e:
            print(f"  {YELLOW}⚠ Warning running {agy_bin}: {e}{RESET}")

    print(f"  {YELLOW}⚡ Antigravity CLI is not yet installed. Running automatic installer...{RESET}")
    try:
        if IS_WINDOWS:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                   "irm https://antigravity.google/cli/install.ps1 | iex"]
            subprocess.run(cmd, check=True)
        else:
            cmd = ["bash", "-c", "curl -fsSL https://antigravity.google/cli/install.sh | bash"]
            subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"  {RED}❌ Automatic installation of Antigravity CLI failed: {e}{RESET}")
        print(f"  You can install it manually from: https://antigravity.google/cli")

    agy_bin = find_agy()
    if shutil.which(agy_bin) or Path(agy_bin).exists():
        _ensure_unix_global_symlink(agy_bin)
        print(f"  {GREEN}✔ Antigravity CLI installed successfully: {agy_bin}{RESET}")
    else:
        print(f"  {YELLOW}⚠ `agy` binary not found in standard PATH. Please ensure it is installed.{RESET}")
    return agy_bin


def _is_agy_onboarded() -> bool:
    """Check whether Antigravity CLI has completed Google login & onboarding."""
    candidates = [
        Path.home() / ".gemini" / "antigravity-cli" / "cache" / "onboarding.json",
        Path.home() / ".gemini" / "antigravity" / "cache" / "onboarding.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("onboardingComplete") or data.get("consumerOnboardingComplete") or data.get("enterpriseOnboardingComplete"):
                    return True
            except Exception:
                pass
    return False


def check_agy_auth(agy_bin: str) -> list:
    """Verify that Antigravity CLI is authenticated with Google and list models."""
    print(f"\n{BOLD}[2/5] Antigravity CLI Authentication & Google Account...{RESET}")
    models = []
    if not (shutil.which(agy_bin) or Path(agy_bin).exists()):
        print(f"  {YELLOW}⚠ Antigravity CLI not found; skipping auth verification.{RESET}")
        return models

    agy_env = {**os.environ, "HOME": os.environ.get("HOME") or str(Path.home())}
    if not IS_WINDOWS:
        agy_env.setdefault("SSH_CONNECTION", "1")

    def _try_list_models():
        try:
            res = subprocess.run([agy_bin, "models"], capture_output=True, text=True, timeout=20, env=agy_env)
            out = (res.stdout or "").strip()
            parsed = []
            for line in out.splitlines():
                if "\t" in line:
                    mid, mname = line.split("\t", 1)
                    parsed.append((mid.strip(), mname.strip()))
            return parsed, out + "\n" + (res.stderr or "")
        except Exception as exc:
            return [], str(exc)

    models, _ = _try_list_models()
    onboarded = _is_agy_onboarded()

    if onboarded and models:
        print(f"  {GREEN}✔ Active Google Antigravity session verified ({len(models)} models available)!{RESET}")
        for mid, mname in models[:6]:
            print(f"    • {mname} ({mid})")
        reauth = input("  Would you like to connect a different Google account? [y/N]: ").strip().lower()
        if reauth not in ("y", "yes", "o", "oui"):
            return models

    print(f"  {YELLOW}⚠ Google account authentication required for Antigravity CLI.{RESET}")
    print(f"  We will launch `{agy_bin}` interactively to display your Google sign-in URL.")
    print(f"  {CYAN}Instructions (especially over SSH server):{RESET}")
    print("    1. Open the displayed Google URL in your browser and sign in.")
    print(
        "    2. If the browser redirects to a `http://localhost:...` page on a remote server,\n"
        f"       {BOLD}copy the full `http://localhost:...` URL from the address bar{RESET} and paste it into this terminal."
    )
    print(f"    3. Once the Antigravity CLI connects, press {BOLD}Ctrl+C{RESET} (or type {BOLD}/exit{RESET}) to resume setup!\n")
    ans = input("  Press [Enter] to launch Google sign-in (or 's' to skip): ").strip().lower()
    if ans != "s":
        try:
            subprocess.run([agy_bin], env=agy_env)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"  {YELLOW}Note: {e}{RESET}")
        models, _ = _try_list_models()
        if _is_agy_onboarded():
            print(f"\n  {GREEN}✔ Google Antigravity authentication confirmed ({len(models)} models available)!{RESET}")
        else:
            print(f"\n  {YELLOW}ℹ You can authenticate at any time in terminal by running: {BOLD}agy{RESET}")

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
    print(f"\n  📲 Open Telegram and send {BOLD}/start{RESET} to {CYAN}@{bot_username}{RESET} now!")
    print("  ⏳ Waiting for your message on Telegram (60s timeout, Ctrl+C to skip)...")
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
                                        "text": f"✅ *Administrator Linked Successfully!*\n\nHello *{uname}* (`{uid}`), your Antigravity v4.2 agent is now connected to your Telegram account.",
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
        print("\n  ⏹ Automatic detection interrupted.")
    return None, None


def configure_telegram_and_admin() -> tuple[str, int | None, str]:
    """Prompt for Telegram token and Admin ID."""
    print(f"\n{BOLD}[3/5] Telegram Bot Configuration...{RESET}")
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
        ans = input(f"  Existing token detected ({masked}). Keep it? [Y/n]: ").strip().lower()
        if ans not in ("", "y", "yes", "o", "oui"):
            token = ""
        else:
            bot_info = validate_telegram_token(token)

    while not bot_info:
        print(f"  💡 Create a bot or retrieve your token from {CYAN}@BotFather{RESET} on Telegram.")
        token = input(f"  🔑 Enter your {BOLD}TELEGRAM_BOT_TOKEN{RESET}: ").strip().strip('"').strip("'")
        bot_info = validate_telegram_token(token)
        if bot_info:
            print(f"  {GREEN}✔ Valid token! Bot connected: {bot_info.get('first_name')} (@{bot_info.get('username')}){RESET}")
        else:
            print(f"  {RED}❌ Invalid token or unable to reach Telegram API. Please try again.{RESET}")

    bot_username = bot_info.get("username", "your_bot")

    print(f"\n{BOLD}[4/5] Administrator Account Setup...{RESET}")
    print("  How would you like to link your Telegram Administrator account?")
    print(f"    {BOLD}1{RESET}) Auto-detect by sending `/start` to @{bot_username} now (Recommended)")
    print(f"    {BOLD}2{RESET}) Enter Telegram User ID manually")
    print(f"    {BOLD}3{RESET}) Auto-claim on the first `/start` after bot launch")
    choice = input("  Your choice [1/2/3] (default: 1): ").strip() or "1"

    admin_id = None
    admin_name = "Admin"

    if choice == "1":
        admin_id, detected_name = poll_admin_from_telegram(token, bot_username)
        if admin_id:
            admin_name = detected_name or "Admin"
            print(f"  {GREEN}✔ Administrator linked automatically: {admin_name} (ID: {admin_id}){RESET}")
        else:
            print(f"  {YELLOW}⚠ No message received. The first user who sends `/start` will claim Administrator.{RESET}")
    elif choice == "2":
        raw_id = input("  🆔 Enter your numeric Telegram User ID (e.g. 123456789): ").strip()
        if raw_id.isdigit():
            admin_id = int(raw_id)
            admin_name = input("  👤 Your Admin name/handle (default: Admin): ").strip() or "Admin"
            print(f"  {GREEN}✔ Administrator configured: {admin_name} (ID: {admin_id}){RESET}")
        else:
            print(f"  {YELLOW}⚠ Non-numeric ID. The first user who sends `/start` will claim Administrator.{RESET}")
    else:
        print(f"  {GREEN}✔ Auto-claim enabled: First user to send `/start` to @{bot_username} becomes Administrator.{RESET}")

    return token, admin_id, admin_name


def _ensure_nodejs_available() -> bool:
    """Ensure Node.js / npx is installed so MCP servers can run."""
    if shutil.which("npx") or shutil.which("npx.cmd"):
        return True
    print(f"  {YELLOW}⚡ Node.js (`npx`) is required for MCP servers. Attempting automatic installation...{RESET}")
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
        print(f"  {YELLOW}⚠ Could not install Node.js automatically: {e}{RESET}")
    return bool(shutil.which("npx") or shutil.which("npx.cmd"))


def configure_mcp_and_skills(agy_bin: str) -> List[str]:
    """Install the built-in Telegram Bot Mastery skill and offer recommended MCP servers."""
    print(f"\n{BOLD}[5/5] Built-in Skills & Recommended MCP Servers...{RESET}")

    # 1. Install built-in telegram-bot-mastery skill
    skill_path = config.ensure_default_skill_installed()
    if skill_path:
        print(f"  {GREEN}✔ Default mastery skill installed:{RESET} {BOLD}telegram-bot-mastery{RESET}")
        print(f"    (Equips the AI with full bot knowledge, multimedia sending, long-term memory, etc.)")

    # 2. Recommended MCP Servers Catalog
    catalog = config.RECOMMENDED_MCP_SERVERS
    print(f"\n  {CYAN}{BOLD}🔌 Recommended MCP Servers Catalog:{RESET}")
    default_nums = []
    for idx, srv in enumerate(catalog, start=1):
        star = f"{GREEN}[Recommended]{RESET}" if srv.get("default_selected") else f"{YELLOW}[Optional]{RESET}"
        if srv.get("default_selected"):
            default_nums.append(str(idx))
        print(f"    {BOLD}{idx}{RESET}) {BOLD}{srv['title']}{RESET} {star}")
        print(f"       └ {srv['description']}")

    default_str = ",".join(default_nums)
    print(f"\n  💡 Enter server numbers separated by commas (e.g. {BOLD}1,2,3{RESET}),")
    print(f"     press {BOLD}[Enter]{RESET} to install the recommended set ({BOLD}{default_str}{RESET}), or type {BOLD}n{RESET} to skip.")
    raw_sel = input(f"  Your choice [{default_str} / all / n]: ").strip().lower()

    if raw_sel in ("n", "no", "non", "s", "skip", "0"):
        print(f"  {YELLOW}ℹ MCP server setup skipped (you can manage and add them anytime via /mcp in Telegram).{RESET}")
        return []

    selected_indices: List[int] = []
    if raw_sel in ("", "y", "yes", "o", "oui"):
        selected_indices = [int(x) for x in default_nums]
    elif raw_sel in ("a", "all"):
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
                prompt_txt = srv.get("env_prompt") or f"{env_key} key (Press Enter to skip)"
                env_val = input(f"  🔑 [{srv_id}] {prompt_txt}: ").strip()
                if env_val:
                    config.update_env_var(env_key, env_val)

        cmd = [agy_bin, "mcp", "add"]
        if env_key and env_val:
            cmd.extend(["--env", f"{env_key}={env_val}"])
        cmd.extend([srv_id, "--", npx_cmd] + list(srv["args"]))

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                print(f"  {GREEN}✔ MCP server '{srv_id}' configured successfully!{RESET}")
                installed_mcp.append(srv_id)
            else:
                err_txt = (res.stderr or res.stdout or "").strip()
                print(f"  {YELLOW}⚠ MCP notice for '{srv_id}': {err_txt}{RESET}")
        except Exception as e:
            print(f"  {YELLOW}⚠ Could not add MCP server '{srv_id}': {e}{RESET}")

    return installed_mcp


def save_configuration(agy_bin: str, token: str, admin_id: int | None, admin_name: str, models: list, installed_mcp: List[str] | None = None):
    """Write .env, settings.json, and users.json safely with clean English defaults."""
    from config import DEFAULT_SETTINGS
    extra_env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                if k not in ("TELEGRAM_BOT_TOKEN", "ALLOWED_USER_ID", "AGY_BIN_PATH", "WORKSPACE_DIR"):
                    extra_env[k] = v.strip()

    env_lines = [
        "# Antigravity Telegram Agent v4.2 Configuration",
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

    # Universal default: "auto" works on Free, Pro, and Ultra Google accounts!
    default_model = "auto"

    settings = DEFAULT_SETTINGS.copy()
    settings["model"] = default_model
    settings["account_tier"] = "auto"
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
    print(f"{GREEN}{BOLD}   ✅ SETUP COMPLETED SUCCESSFULLY!                              {RESET}")
    print(f"{GREEN}{BOLD}=================================================================={RESET}")
    print(f"  • Environment {BOLD}.env{RESET} file generated")
    print(f"  • Settings {BOLD}settings.json{RESET} initialized (Model: {settings.get('model')}, Tier: {settings.get('account_tier')})")
    print(f"  • User access file {BOLD}users.json{RESET} ready")
    print(f"  • AI Skill {BOLD}telegram-bot-mastery{RESET} active")
    if installed_mcp:
        print(f"  • Configured MCP servers: {BOLD}{', '.join(installed_mcp)}{RESET}")
    print(f"\n  🚀 You can configure {BOLD}all settings, models, and MCP servers{RESET} directly in Telegram with {CYAN}/settings{RESET}, {CYAN}/usage{RESET}, and {CYAN}/mcp{RESET}!\n")


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
        print(f"\n{YELLOW}Setup interrupted by user.{RESET}")
        sys.exit(1)
