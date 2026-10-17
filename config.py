"""
config.py - Universal Cross-Platform Configuration Engine for Antigravity Telegram Bot
Supports Windows (10/11/Server), Linux (Ubuntu/Debian/Armbian/Oracle/Arch), and macOS.
Zero hardcoded personal data — 100% public-repository safe.
"""

import os
import sys
import json
import socket
import shutil
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

logger = logging.getLogger("config")

IS_WINDOWS = (os.name == "nt")
IS_MACOS = (sys.platform == "darwin")
IS_LINUX = not IS_WINDOWS and not IS_MACOS

# Prioritize IPv4 (AF_INET) over IPv6 (AF_INET6) to prevent [Errno 101] Network is unreachable
# on Linux/Armbian boxes where IPv6 AAAA records exist (e.g. api.telegram.org) but IPv6 routing is absent.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_preferred_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    res = _orig_getaddrinfo(host, port, family, type, proto, flags)
    ipv4 = [r for r in res if r[0] == socket.AF_INET]
    ipv6 = [r for r in res if r[0] != socket.AF_INET]
    return ipv4 + ipv6 if ipv4 else res


socket.getaddrinfo = _ipv4_preferred_getaddrinfo

# Base directory: defaults to current script directory, or BOT_BASE_DIR if specified
_script_dir = Path(__file__).resolve().parent
BASE_DIR = Path(os.getenv("BOT_BASE_DIR", str(_script_dir))).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)

ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)
else:
    load_dotenv()

# Temporary directory for media downloads & transient files (cross-platform safe)
TEMP_DIR = BASE_DIR / "tmp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Default Workspace directory for the agent
_raw_ws = os.getenv("WORKSPACE_DIR", "").strip()
if _raw_ws and (not IS_WINDOWS or not _raw_ws.startswith("/")):
    _ws_candidate = Path(_raw_ws)
else:
    _ws_candidate = Path.home()

try:
    if not _ws_candidate.exists():
        _ws_candidate = Path.home()
except Exception:
    _ws_candidate = BASE_DIR

WORKSPACE_DIR = _ws_candidate.resolve()


def find_agy_binary(configured_path: Optional[str] = None) -> Optional[str]:
    """
    Locate the Antigravity CLI ('agy' / 'agy.exe') binary across Windows, Linux, and macOS.
    Checks:
      1. Explicitly configured path or AGY_BIN_PATH env variable
      2. System PATH via shutil.which
      3. Standard Windows installation directories (%LOCALAPPDATA%\\agy\\bin\\agy.exe)
      4. Standard Unix installation directories (~/.local/bin/agy, /usr/local/bin/agy)
    """
    candidates: List[str] = []
    if configured_path:
        candidates.append(configured_path.strip())
    env_bin = os.getenv("AGY_BIN_PATH", "").strip()
    if env_bin:
        candidates.append(env_bin)

    for c in candidates:
        if not c:
            continue
        # Avoid Unix hardcoded default on Windows
        if IS_WINDOWS and c.startswith("/"):
            continue
        resolved = shutil.which(c)
        if resolved:
            return resolved
        p = Path(c)
        if p.is_file():
            return str(p.resolve())

    # Search standard PATH
    for name in ("agy.exe", "agy") if IS_WINDOWS else ("agy",):
        found = shutil.which(name)
        if found:
            return found

    # Search known platform-specific locations
    search_paths: List[Path] = []
    if IS_WINDOWS:
        local_app_data = os.getenv("LOCALAPPDATA", "")
        user_profile = os.getenv("USERPROFILE", str(Path.home()))
        if local_app_data:
            search_paths.append(Path(local_app_data) / "agy" / "bin" / "agy.exe")
            search_paths.append(Path(local_app_data) / "Programs" / "agy" / "agy.exe")
        search_paths.append(Path(user_profile) / ".local" / "bin" / "agy.exe")
        search_paths.append(Path(user_profile) / "AppData" / "Local" / "agy" / "bin" / "agy.exe")
    else:
        home = Path.home()
        search_paths.extend([
            home / ".local" / "bin" / "agy",
            Path("/usr/local/bin/agy"),
            Path("/root/.local/bin/agy"),
            Path("/usr/bin/agy"),
            Path("/opt/antigravity/bin/agy"),
        ])

    for sp in search_paths:
        try:
            if sp.is_file():
                return str(sp.resolve())
        except Exception:
            continue

    return None


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_raw_user = os.getenv("ALLOWED_USER_ID", "").strip()
ALLOWED_USER_ID = int(_raw_user) if _raw_user.isdigit() else 0

AGY_BIN_PATH = find_agy_binary() or ("agy.exe" if IS_WINDOWS else "agy")

# State & Configuration Files
SETTINGS_FILE = BASE_DIR / "settings.json"
CUSTOM_COMMANDS_FILE = BASE_DIR / "custom_commands.json"
CONVERSATIONS_FILE = BASE_DIR / "conversations.json"
TRANSIENT_MSGS_FILE = TEMP_DIR / "tg_transient_msgs.json"
TURN_SENT_FILES_FILE = TEMP_DIR / "tg_turn_sent_files.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "agent_name": os.getenv("AGENT_NAME", "Antigravity Agent"),
    "mode": "auto-approve",           # "auto-approve" (--dangerously-skip-permissions), "accept-edits", "plan"
    "model": "gemini-4-argon-medium", # Dynamically synced with `agy models`
    "effort": "auto",                 # "auto", "low", "medium", "high", "xhigh", "max"
    "timeout": 600,                   # Timeout in seconds (0 = infinite)
    "sandbox": False,                 # Run with --sandbox terminal restrictions
    "multi_agent": True,              # Enable multi-agent / subagent swarm capabilities
    "agent_profile": "",              # Optional --agent flag value
    "remote_control": False,          # Enable --remote-control session flag
    "verbosity": "normal",            # "compact", "normal", "detailed"
    "auto_send_files": True,          # Automatically send generated files/images/videos/audio to Telegram
    "workspace_dir": str(WORKSPACE_DIR),
    "extra_dirs": [],                 # Additional directories passed via --add-dir
    "custom_instructions": "",        # Optional custom system prompt instructions set from Telegram
}


def load_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_SETTINGS, **data}
                # Ensure workspace_dir is valid on current OS
                ws = merged.get("workspace_dir", "")
                if not ws or (IS_WINDOWS and ws.startswith("/")) or not Path(ws).exists():
                    merged["workspace_dir"] = str(WORKSPACE_DIR)
                return merged
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(new_settings: Dict[str, Any]) -> bool:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, indent=2, ensure_ascii=False)
        tmp.replace(SETTINGS_FILE)
        return True
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return False


def update_env_var(key: str, value: str) -> bool:
    """Safely add or update a key=value pair in the .env file."""
    try:
        lines: List[str] = []
        found = False
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines: List[str] = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{key}={value}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.environ[key] = str(value)
        return True
    except Exception as e:
        logger.error(f"Error updating .env key {key}: {e}")
        return False


def update_allowed_user(user_id: int) -> None:
    global ALLOWED_USER_ID
    ALLOWED_USER_ID = int(user_id)
    update_env_var("ALLOWED_USER_ID", str(user_id))


def load_conversations() -> List[Dict[str, Any]]:
    """Load recent Antigravity CLI conversation history metadata."""
    if CONVERSATIONS_FILE.exists():
        try:
            with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f"Error loading conversations: {e}")
    return []


def record_conversation(
    conversation_id: str,
    prompt_preview: str,
    model: str,
    tokens: int = 0
) -> None:
    """Record or update a conversation entry in conversations.json (keeps last 25)."""
    if not conversation_id:
        return
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    convs = load_conversations()
    existing = next((c for c in convs if c.get("id") == conversation_id), None)
    clean_preview = " ".join(prompt_preview.strip().split())[:80]
    if existing:
        existing["updated_at"] = now_str
        existing["model"] = model
        existing["turns"] = int(existing.get("turns", 1)) + 1
        existing["total_tokens"] = int(existing.get("total_tokens", 0)) + int(tokens)
        if clean_preview and not existing.get("title"):
            existing["title"] = clean_preview
    else:
        convs.insert(0, {
            "id": conversation_id,
            "title": clean_preview or "Nouvelle session",
            "model": model,
            "created_at": now_str,
            "updated_at": now_str,
            "turns": 1,
            "total_tokens": int(tokens),
        })
    convs = convs[:25]
    try:
        with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(convs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Error saving conversations: {e}")
