"""
group_manager.py - Universal Autonomous Group & Channel Intelligence System
Provides 100% customizable, unconstrained group access for the AI agent:
- Stealth Passive Observation (listens and logs context, 100% silent in groups)
- Interactive Mode (responds strictly when @mentioned or assigned)
- Customizable Missions & Roles per group (monitoring, homework, support, alerts, standups)
- Ring-buffer message logging so the AI agent can recall and answer questions about group events
- Full Admin Authorization workflow with 1-click group departure (/groups)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from config import BASE_DIR

logger = logging.getLogger("group_manager")

GROUPS_FILE = BASE_DIR / "groups.json"

MODE_PASSIVE = "passive"    # Silent surveillance & intel gathering (CANNOT write to group)
MODE_ACTIVE = "active"      # Interactive, responds when @mentioned or assigned
MODE_DISABLED = "disabled"  # Ignored completely

MAX_RECENT_MESSAGES_PER_GROUP = 60


class GroupManager:
    """Manages group chat authorizations, operational modes, custom missions, and message history."""

    def __init__(self, file_path: Path = GROUPS_FILE):
        self.file_path = file_path
        self._groups: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.is_file():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._groups = data
                    return
            except Exception as e:
                logger.error(f"Error loading {self.file_path}: {e}")
        self._groups = {}

    def _save(self) -> bool:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._groups, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.file_path)
            return True
        except Exception as e:
            logger.error(f"Error saving {self.file_path}: {e}")
            return False

    def get_group(self, chat_id: int) -> Optional[Dict[str, Any]]:
        return self._groups.get(str(chat_id))

    def register_or_update_group(
        self,
        chat_id: int,
        title: str,
        chat_type: str,
        added_by_id: int = 0,
        added_by_name: str = "",
        auto_authorize_if_admin: bool = False,
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Register a new group/channel or update its title.
        Defaults to PASSIVE mode (safe silent observation, no writing).
        Returns (group_data, is_new).
        """
        s_id = str(chat_id)
        now_iso = datetime.now().isoformat()
        is_new = False

        if s_id not in self._groups:
            is_new = True
            self._groups[s_id] = {
                "chat_id": chat_id,
                "title": title or f"Group {chat_id}",
                "type": chat_type,
                "is_authorized": auto_authorize_if_admin,
                "mode": MODE_PASSIVE,  # Safe default: listen only, never write
                "can_read": True,
                "can_write": False,
                "mission": "",         # Freeform mission for the agent (e.g. "Monitor homework", "Customer support")
                "status": "active",
                "added_by_id": added_by_id,
                "added_by_name": added_by_name,
                "created_at": now_iso,
                "updated_at": now_iso,
                "recent_messages": [], # Ring buffer of recent messages
            }
            logger.info(f"Registered new group '{title}' (ID: {chat_id}) in PASSIVE mode.")
        else:
            g = self._groups[s_id]
            if title and g.get("title") != title:
                g["title"] = title
            g["status"] = "active"
            g["updated_at"] = now_iso
            if "recent_messages" not in g:
                g["recent_messages"] = []

        self._save()
        return self._groups[s_id], is_new

    def record_message(
        self,
        chat_id: int,
        sender_name: str,
        sender_id: int,
        text: str,
    ) -> None:
        """Record an incoming message into the group's ring buffer for AI recall."""
        s_id = str(chat_id)
        if s_id not in self._groups:
            return

        if not text or len(text.strip()) == 0:
            return

        g = self._groups[s_id]
        if "recent_messages" not in g:
            g["recent_messages"] = []

        msg_entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sender_name": sender_name or "Member",
            "sender_id": sender_id,
            "text": text.strip()[:600],
        }
        g["recent_messages"].append(msg_entry)
        if len(g["recent_messages"]) > MAX_RECENT_MESSAGES_PER_GROUP:
            g["recent_messages"].pop(0)

        g["updated_at"] = datetime.now().isoformat()
        self._save()

    def set_mode(self, chat_id: int, mode: str) -> bool:
        s_id = str(chat_id)
        if s_id not in self._groups:
            return False
        if mode not in (MODE_PASSIVE, MODE_ACTIVE, MODE_DISABLED):
            mode = MODE_PASSIVE

        self._groups[s_id]["mode"] = mode
        if mode == MODE_PASSIVE:
            self._groups[s_id]["can_read"] = True
            self._groups[s_id]["can_write"] = False
        elif mode == MODE_ACTIVE:
            self._groups[s_id]["can_read"] = True
            self._groups[s_id]["can_write"] = True
        elif mode == MODE_DISABLED:
            self._groups[s_id]["can_read"] = False
            self._groups[s_id]["can_write"] = False

        self._groups[s_id]["updated_at"] = datetime.now().isoformat()
        self._save()
        logger.info(f"Group {chat_id} mode changed to {mode}.")
        return True

    def set_authorization(self, chat_id: int, authorized: bool) -> bool:
        s_id = str(chat_id)
        if s_id not in self._groups:
            return False
        self._groups[s_id]["is_authorized"] = bool(authorized)
        self._groups[s_id]["updated_at"] = datetime.now().isoformat()
        self._save()
        return True

    def set_mission(self, chat_id: int, mission: str) -> bool:
        """Set custom role / mission / instructions for the agent regarding this group."""
        s_id = str(chat_id)
        if s_id not in self._groups:
            return False
        self._groups[s_id]["mission"] = mission.strip()
        self._groups[s_id]["updated_at"] = datetime.now().isoformat()
        self._save()
        return True

    def toggle_permission(self, chat_id: int, perm: str) -> bool:
        s_id = str(chat_id)
        if s_id not in self._groups:
            return False
        if perm in ("can_read", "can_write"):
            cur = bool(self._groups[s_id].get(perm, False))
            self._groups[s_id][perm] = not cur
            self._groups[s_id]["updated_at"] = datetime.now().isoformat()
            self._save()
            return self._groups[s_id][perm]
        return False

    def can_read(self, chat_id: int) -> bool:
        g = self.get_group(chat_id)
        if not g:
            return True  # Allow safe passive reading so intelligence works immediately
        if g.get("mode") == MODE_DISABLED:
            return False
        return bool(g.get("can_read", True))

    def can_write(self, chat_id: int) -> bool:
        """
        Strict check: can the bot send ANY message into this group?
        Returns False for PASSIVE, DISABLED, or UNAUTHORIZED groups.
        """
        g = self.get_group(chat_id)
        if not g:
            return False
        if not g.get("is_authorized", False):
            return False
        if g.get("mode") != MODE_ACTIVE:
            return False
        return bool(g.get("can_write", False))

    def get_group_mode(self, chat_id: int) -> str:
        g = self.get_group(chat_id)
        if not g:
            return MODE_PASSIVE
        return str(g.get("mode", MODE_PASSIVE))

    def get_recent_messages(self, chat_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        g = self.get_group(chat_id)
        if not g:
            return []
        msgs = g.get("recent_messages", [])
        return msgs[-limit:]

    def get_groups_context_for_agent(self, user_query: str) -> str:
        """
        Dynamically extracts group context for the agent if the query touches groups,
        discussions, lessons, homework, support, or recent group activity.
        """
        if not self._groups:
            return ""

        lower = user_query.lower()
        active_groups = [g for g in self._groups.values() if g.get("status") != "left" and g.get("can_read", True)]
        if not active_groups:
            return ""

        # Check if query references any group specifically or generally
        is_group_query = any(k in lower for k in [
            "group", "groupe", "classe", "class", "channel", "canal", "discussion",
            "cours", "leçon", "lesson", "devoir", "homework", "qu'est-ce qu'on a dit",
            "what was said", "résumé", "summary", "messages", "prof", "teacher",
            "annonces", "announcements"
        ])

        matched_groups = []
        for g in active_groups:
            t_lower = g.get("title", "").lower()
            if t_lower and t_lower in lower:
                matched_groups.append(g)

        if not matched_groups and is_group_query:
            matched_groups = active_groups

        if not matched_groups:
            return ""

        lines = ["[TELEGRAM GROUPS CONTEXT & RECENT DISCUSSIONS]"]
        for g in matched_groups[:3]:
            title = g.get("title", f"Group {g.get('chat_id')}")
            mission = g.get("mission", "").strip()
            mode = g.get("mode", "passive")
            can_w = "Yes" if g.get("can_write") else "No (Listen-Only)"

            lines.append(f"\n📁 Group: '{title}' (ID: {g.get('chat_id')}) [Mode: {mode}, Can Write: {can_w}]")
            if mission:
                lines.append(f"  🎯 Custom Mission for this group: {mission}")

            msgs = g.get("recent_messages", [])
            if msgs:
                lines.append("  💬 Recent messages in group:")
                for m in msgs[-15:]:
                    lines.append(f"    - [{m.get('time', '')}] {m.get('sender_name', 'Member')}: {m.get('text', '')}")
            else:
                lines.append("  <i>No messages logged yet for this group.</i>")

        lines.append(
            "\nInstruction: You have full access to the actual messages from these Telegram groups. "
            "Use them autonomously to summarize, extract tasks/homework, answer questions, or formulate advice as requested by the user."
        )
        return "\n".join(lines)

    def mark_left(self, chat_id: int) -> None:
        s_id = str(chat_id)
        if s_id in self._groups:
            self._groups[s_id]["status"] = "left"
            self._groups[s_id]["updated_at"] = datetime.now().isoformat()
            self._save()

    def remove_group(self, chat_id: int) -> bool:
        s_id = str(chat_id)
        if s_id in self._groups:
            del self._groups[s_id]
            self._save()
            return True
        return False

    def list_groups(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._groups)


group_mgr = GroupManager()
