"""
log_scanner.py - Autonomous Log Monitor & Self-Healing Engine for Magma Box
Scans Docker containers and systemd services for crashes, OOMs, and critical errors.
Dispatches actionable diagnostic prompts to Magma Agent with anti-loop cooldowns.
Provides granular user control (global toggle and per-service toggle via Telegram).
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Callable, Awaitable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from config import BASE_DIR, ALLOWED_USER_ID

logger = logging.getLogger("log_scanner")
PM = ParseMode.HTML

CONFIG_FILE = BASE_DIR / "auto_heal_config.json"
INCIDENTS_LOG_FILE = BASE_DIR / "incidents_history.json"

DEFAULT_AUTO_HEAL_CONFIG = {
    "enabled": True,
    "scan_interval_seconds": 60,
    "cooldown_minutes": 15,
    "services": {
        "docker": {
            "name": "Docker Daemon",
            "type": "systemd",
            "target": "docker",
            "enabled": True,
            "icon": "🐳"
        },
        "antigravity-bot": {
            "name": "Bot Telegram",
            "type": "systemd",
            "target": "antigravity-bot",
            "enabled": False,  # Off by default to avoid recursive auto-heals
            "icon": "🤖"
        }
    }
}

# Critical error patterns indicating actionable crashes or service failures
CRITICAL_PATTERNS = [
    r"\bfatal\b",
    r"\bpanic:\b",
    r"\bsegmentation fault\b",
    r"\bout of memory\b",
    r"\boomkilled\b",
    r"\bkilled by signal\b",
    r"\bdatabase\s+disk\s+image\s+is\s+malformed\b",
    r"\bsqlite.*error\b",
    r"\bconnection\s+refused\b",
    r"\baddress\s+already\s+in\s+use\b",
    r"\bfailed\s+to\s+bind\b",
    r"\bread-only\s+file\s+system\b",
    r"\bno\s+space\s+left\s+on\s+device\b",
    r"\bunhandled\s+exception\b",
    r"\bcore\s+dumped\b",
    r"\bexited\s+with\s+status\s+[1-9]\b"
]

# Patterns to filter out (normal operational logs, non-critical warnings)
IGNORED_PATTERNS = [
    r"404\s+not\s+found",
    r"deprecationwarning",
    r"userwarning",
    r"info:",
    r"debug:",
    r"certificate\s+will\s+expire",
    r"session\s+expired"
]


class LogScanner:
    def __init__(self):
        self.config: Dict[str, Any] = self._load_config()
        self.last_triggers: Dict[str, float] = {}  # service_key -> timestamp
        self.last_error_hashes: Dict[str, str] = {}  # service_key -> md5 hash
        self.incidents_history: List[Dict[str, Any]] = self._load_incidents()
        self.is_scanning_active: bool = False
        self._dispatch_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None

    def _load_config(self) -> Dict[str, Any]:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge with default services if missing
                    merged = {**DEFAULT_AUTO_HEAL_CONFIG, **data}
                    for k, v in DEFAULT_AUTO_HEAL_CONFIG["services"].items():
                        if k not in merged["services"]:
                            merged["services"][k] = v
                    return merged
            except Exception as e:
                logger.error(f"Error reading {CONFIG_FILE}: {e}")
        self._save_config_raw(DEFAULT_AUTO_HEAL_CONFIG)
        return DEFAULT_AUTO_HEAL_CONFIG.copy()

    def _save_config_raw(self, cfg: Dict[str, Any]) -> bool:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving {CONFIG_FILE}: {e}")
            return False

    def save_config(self) -> bool:
        return self._save_config_raw(self.config)

    def _load_incidents(self) -> List[Dict[str, Any]]:
        if INCIDENTS_LOG_FILE.exists():
            try:
                with open(INCIDENTS_LOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading incidents history: {e}")
        return []

    def _save_incidents(self) -> None:
        try:
            INCIDENTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Keep only the last 30 incidents
            trimmed = self.incidents_history[-30:]
            with open(INCIDENTS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(trimmed, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving incidents history: {e}")

    def record_incident(self, service_key: str, name: str, error_snippet: str) -> None:
        incident = {
            "service_key": service_key,
            "name": name,
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "error_snippet": error_snippet[:300]
        }
        self.incidents_history.append(incident)
        self._save_incidents()

    def is_global_enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def set_global_enabled(self, enabled: bool) -> None:
        self.config["enabled"] = enabled
        self.save_config()

    def is_service_enabled(self, service_key: str) -> bool:
        if not self.is_global_enabled():
            return False
        srv = self.config.get("services", {}).get(service_key)
        return bool(srv.get("enabled", False)) if srv else False

    def toggle_service(self, service_key: str) -> bool:
        srv = self.config.get("services", {}).get(service_key)
        if srv:
            srv["enabled"] = not srv.get("enabled", False)
            self.save_config()
            return srv["enabled"]
        return False

    def toggle_global(self) -> bool:
        new_val = not self.is_global_enabled()
        self.set_global_enabled(new_val)
        return new_val

    def register_dispatch_callback(self, cb: Callable[[str, str, str], Awaitable[None]]) -> None:
        """Register the async function that invokes Magma Agent for Auto-Heal."""
        self._dispatch_callback = cb

    async def _run_command(self, cmd: list) -> Tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return (
                proc.returncode,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip()
            )
        except Exception as e:
            return 1, "", str(e)

    async def fetch_service_logs(self, service_conf: dict) -> str:
        stype = service_conf.get("type", "container")
        target = service_conf.get("target", "")
        if not target:
            return ""

        if stype == "container":
            # Fetch last 40 lines of container logs
            rc, out, err = await self._run_command(["docker", "logs", "--tail", "40", target])
            combined = (out + "\n" + err).strip()
            return combined
        elif stype == "systemd":
            # Fetch recent logs from systemd journal
            rc, out, _ = await self._run_command([
                "journalctl", "-u", target, "-n", "40", "--no-pager"
            ])
            return out
        return ""

    def analyze_logs_for_errors(self, logs: str) -> Optional[str]:
        """
        Parses log content looking for high-severity crash signatures.
        Returns the relevant error snippet if found, None otherwise.
        """
        if not logs:
            return None

        lines = logs.splitlines()
        critical_lines = []

        for line in lines:
            lower = line.lower()
            if any(re.search(pat, lower) for pat in IGNORED_PATTERNS):
                continue
            if any(re.search(pat, lower) for pat in CRITICAL_PATTERNS):
                critical_lines.append(line.strip())

        if critical_lines:
            return "\n".join(critical_lines[-6:])
        return None

    def is_in_cooldown(self, service_key: str, error_snippet: str) -> bool:
        cooldown_secs = self.config.get("cooldown_minutes", 15) * 60
        now = time.time()
        last_time = self.last_triggers.get(service_key, 0)

        if (now - last_time) < cooldown_secs:
            return True

        err_hash = hashlib.md5(error_snippet.encode("utf-8")).hexdigest()
        last_hash = self.last_error_hashes.get(service_key, "")
        if err_hash == last_hash and (now - last_time) < 1800:
            return True

        return False

    async def scan_all_services(self) -> List[Tuple[str, dict, str]]:
        """
        Scans all enabled services.
        Returns a list of tuples: (service_key, service_conf, error_snippet).
        """
        if not self.is_global_enabled():
            return []

        detected_issues = []
        services = self.config.get("services", {})

        for s_key, s_conf in services.items():
            if not s_conf.get("enabled", False):
                continue

            try:
                logs = await self.fetch_service_logs(s_conf)
                error_snippet = self.analyze_logs_for_errors(logs)
                if error_snippet:
                    if not self.is_in_cooldown(s_key, error_snippet):
                        detected_issues.append((s_key, s_conf, error_snippet))
            except Exception as ex:
                logger.warning(f"Error scanning service {s_key}: {ex}")

        return detected_issues

    async def perform_scheduled_scan(self) -> None:
        """Scheduled routine called by the background loop."""
        if not self.is_global_enabled() or not self._dispatch_callback:
            return

        issues = await self.scan_all_services()
        now = time.time()

        for s_key, s_conf, err_snippet in issues:
            self.last_triggers[s_key] = now
            self.last_error_hashes[s_key] = hashlib.md5(err_snippet.encode("utf-8")).hexdigest()
            self.record_incident(s_key, s_conf.get("name", s_key), err_snippet)

            logger.info(f"🚨 Critical error detected for {s_key}, triggering Auto-Heal...")
            try:
                await self._dispatch_callback(s_key, s_conf.get("name", s_key), err_snippet)
            except Exception as e:
                logger.error(f"Failed dispatching auto-heal for {s_key}: {e}")

    def get_dashboard_keyboard(self) -> InlineKeyboardMarkup:
        """Builds the interactive Telegram dashboard keyboard."""
        global_on = self.is_global_enabled()
        global_btn_text = "🟢 Auto-Heal IA : ACTIVÉ" if global_on else "🔴 Auto-Heal IA : DÉSACTIVÉ"

        rows = [
            [InlineKeyboardButton(global_btn_text, callback_data="autoheal:toggle_global")]
        ]

        services = self.config.get("services", {})
        service_btns = []
        for s_key, s_conf in services.items():
            name = s_conf.get("name", s_key)
            icon = s_conf.get("icon", "📦")
            is_active = s_conf.get("enabled", False) and global_on
            status_symbol = "✅" if is_active else "❌"
            label = f"{icon} {name} : {status_symbol}"
            service_btns.append(InlineKeyboardButton(label, callback_data=f"autoheal:toggle:{s_key}"))

        for i in range(0, len(service_btns), 2):
            rows.append(service_btns[i:i+2])

        rows.append([
            InlineKeyboardButton("⚡ Scan Immédiat", callback_data="autoheal:scan_now"),
            InlineKeyboardButton("📜 Historique", callback_data="autoheal:history")
        ])
        rows.append([
            InlineKeyboardButton("⬅️ Services", callback_data="srv:refresh"),
            InlineKeyboardButton("❌ Fermer", callback_data="close_menu")
        ])

        return InlineKeyboardMarkup(rows)

    def get_dashboard_text(self) -> str:
        """Returns the explanatory status text for /autoheal."""
        global_on = self.is_global_enabled()
        status_str = "🟢 <b>Actif</b> (Surveillance continue des logs)" if global_on else "🔴 <b>Désactivé</b>"
        cooldown = self.config.get("cooldown_minutes", 15)

        lines = [
            "🛡️ <b>Surveillance des Logs & Auto-Heal IA</b>\n",
            f"• <b>Statut Global :</b> {status_str}",
            f"• <b>Fréquence d'analyse :</b> <i>Toutes les 60 secondes</i>",
            f"• <b>Protection anti-boucle :</b> <i>{cooldown} min de cooldown par service</i>\n",
            "<b>📋 Programmes et Services surveillés :</b>"
        ]

        services = self.config.get("services", {})
        for s_key, s_conf in services.items():
            icon = s_conf.get("icon", "📦")
            name = s_conf.get("name", s_key)
            stype = s_conf.get("type", "container")
            is_active = s_conf.get("enabled", False) and global_on
            state_text = "✅ Surveillé & Auto-Heal" if is_active else "❌ Inactif"
            lines.append(f"• {icon} <b>{name}</b> (<code>{stype}</code>) : {state_text}")

        lines.append("\n<i>Cliquez sur un service ci-dessous pour activer ou couper sa surveillance IA.</i>")
        return "\n".join(lines)


# Global singleton instance
log_scanner = LogScanner()
