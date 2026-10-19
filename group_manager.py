"""
group_manager.py - Group & Channel Authorization and Permissions Manager
Ensures total safety in shared groups and channels:
- Strict silence by default (no unwanted error messages, no 'private bot' spam in school groups)
- Passive Listening mode (intel, homework tracking, course surveillance without ever speaking)
- Interactive mode (responds strictly when @mentioned)
- Admin authorization workflow with one-click group departure (/groups)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from config import BASE_DIR

logger = logging.getLogger("group_manager")

GROUPS_FILE = BASE_DIR / "groups.json"

MODE_PASSIVE = "passive"    # Silent surveillance / homework & lessons listener (CANNOT write)
MODE_ACTIVE = "active"      # Interactive, only responds when explicitly @mentioned
MODE_DISABLED = "disabled"  # Ignored completely


class GroupManager:
    """Manages group chat authorizations, operational modes, and permissions."""

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
                "school_tracking": True,  # Enable school/homework indexing by default
                "status": "active",
                "added_by_id": added_by_id,
                "added_by_name": added_by_name,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            logger.info(f"Registered new group '{title}' (ID: {chat_id}) in PASSIVE mode.")
        else:
            g = self._groups[s_id]
            if title and g.get("title") != title:
                g["title"] = title
            g["status"] = "active"
            g["updated_at"] = now_iso

        self._save()
        return self._groups[s_id], is_new

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

    def toggle_school_tracking(self, chat_id: int) -> bool:
        s_id = str(chat_id)
        if s_id not in self._groups:
            return False
        cur = self._groups[s_id].get("school_tracking", True)
        self._groups[s_id]["school_tracking"] = not cur
        self._groups[s_id]["updated_at"] = datetime.now().isoformat()
        self._save()
        return self._groups[s_id]["school_tracking"]

    def is_school_tracking_enabled(self, chat_id: int) -> bool:
        g = self.get_group(chat_id)
        if not g:
            return True  # Enabled by default for all groups
        return bool(g.get("school_tracking", True))

    def get_group_mode(self, chat_id: int) -> str:
        g = self.get_group(chat_id)
        if not g:
            return MODE_PASSIVE
        return str(g.get("mode", MODE_PASSIVE))

    def can_read(self, chat_id: int) -> bool:
        g = self.get_group(chat_id)
        if not g:
            return True  # Allow safe passive reading so intelligence/homework works immediately
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
            return False  # Unregistered groups are strictly silent
        if not g.get("is_authorized", False):
            return False
        if g.get("mode") != MODE_ACTIVE:
            return False
        return bool(g.get("can_write", False))

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
