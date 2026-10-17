"""
auth_manager.py - Role-Based Access Control (RBAC) & User Management
Manages permissions for Administrators, Pending Requests, and Blocked Users.
Supports automatic First-Admin Onboarding when deployed on a fresh system.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import config
from config import BASE_DIR, update_allowed_user

logger = logging.getLogger("auth_manager")

USERS_FILE = BASE_DIR / "users.json"

ROLE_ADMIN = "admin"
ROLE_PENDING = "pending"
ROLE_BLOCKED = "blocked"

ROLES_DESCRIPTION = {
    ROLE_ADMIN: "👑 Administrateur (Contrôle total de l'Agent)",
    ROLE_PENDING: "⏳ En attente de validation",
    ROLE_BLOCKED: "🚫 Bloqué",
}


def _load_users_raw() -> Dict[str, Dict[str, Any]]:
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error(f"Error reading {USERS_FILE}: {e}")

    initial: Dict[str, Dict[str, Any]] = {}
    if config.ALLOWED_USER_ID:
        uid = str(config.ALLOWED_USER_ID)
        initial[uid] = {
            "name": "Administrateur",
            "username": "",
            "role": ROLE_ADMIN,
            "created_at": str(date.today()),
        }
        _save_users_raw(initial)
    return initial


def _save_users_raw(data: Dict[str, Dict[str, Any]]) -> bool:
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = USERS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(USERS_FILE)
        return True
    except Exception as e:
        logger.error(f"Error saving {USERS_FILE}: {e}")
        return False


class AuthManager:
    def __init__(self):
        self._ensure_admin_registered()

    def _ensure_admin_registered(self) -> None:
        users = _load_users_raw()
        if config.ALLOWED_USER_ID:
            uid = str(config.ALLOWED_USER_ID)
            if uid not in users or users[uid].get("role") != ROLE_ADMIN:
                users[uid] = {
                    "name": users.get(uid, {}).get("name", "Administrateur"),
                    "username": users.get(uid, {}).get("username", ""),
                    "role": ROLE_ADMIN,
                    "created_at": users.get(uid, {}).get("created_at", str(date.today())),
                }
                _save_users_raw(users)

    def has_any_admin(self) -> bool:
        """Returns True if at least one administrator is configured."""
        if config.ALLOWED_USER_ID:
            return True
        users = _load_users_raw()
        return any(u.get("role") == ROLE_ADMIN for u in users.values())

    def claim_initial_admin(self, user_id: int, name: str = "", username: str = "") -> bool:
        """
        If no administrator is configured yet on a fresh install,
        assigns this user as the primary Administrator and saves ALLOWED_USER_ID to .env.
        """
        if self.has_any_admin():
            return False
        update_allowed_user(user_id)
        return self.set_user_role(
            user_id=user_id,
            role=ROLE_ADMIN,
            name=name or "Administrateur",
            username=username or "",
        )

    def get_primary_admin_id(self) -> Optional[int]:
        if config.ALLOWED_USER_ID:
            return int(config.ALLOWED_USER_ID)
        users = _load_users_raw()
        for uid, u in users.items():
            if u.get("role") == ROLE_ADMIN and str(uid).isdigit():
                return int(uid)
        return None

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        self._ensure_admin_registered()
        users = _load_users_raw()
        return users.get(str(user_id))

    def get_user_role(self, user_id: int) -> str:
        uid = str(user_id)
        if config.ALLOWED_USER_ID and uid == str(config.ALLOWED_USER_ID):
            return ROLE_ADMIN
        user = self.get_user(user_id)
        return user.get("role", ROLE_PENDING) if user else ROLE_PENDING

    def is_admin(self, user_id: int) -> bool:
        return self.get_user_role(user_id) == ROLE_ADMIN

    def is_blocked(self, user_id: int) -> bool:
        return self.get_user_role(user_id) == ROLE_BLOCKED

    def register_access_request(self, user_id: int, name: str, username: str = "") -> Tuple[bool, str]:
        users = _load_users_raw()
        uid = str(user_id)
        if uid in users:
            current_role = users[uid].get("role")
            if current_role == ROLE_BLOCKED:
                return (False, "blocked")
            if current_role == ROLE_ADMIN:
                return (True, current_role)

        users[uid] = {
            "name": name or f"User_{uid}",
            "username": username or "",
            "role": ROLE_PENDING,
            "created_at": str(date.today()),
        }
        _save_users_raw(users)
        return (True, ROLE_PENDING)

    def set_user_role(
        self,
        user_id: int,
        role: str,
        name: str = "",
        username: str = "",
    ) -> bool:
        users = _load_users_raw()
        uid = str(user_id)

        if config.ALLOWED_USER_ID and uid == str(config.ALLOWED_USER_ID) and role != ROLE_ADMIN:
            logger.warning("Attempted to demote master admin!")
            return False

        if uid not in users:
            users[uid] = {
                "name": name or f"User_{uid}",
                "username": username or "",
                "role": role,
                "created_at": str(date.today()),
            }
        else:
            users[uid]["role"] = role
            if name:
                users[uid]["name"] = name
            if username:
                users[uid]["username"] = username

        return _save_users_raw(users)

    def remove_user(self, user_id: int) -> bool:
        uid = str(user_id)
        if config.ALLOWED_USER_ID and uid == str(config.ALLOWED_USER_ID):
            return False
        users = _load_users_raw()
        if uid in users:
            del users[uid]
            return _save_users_raw(users)
        return False

    def delete_user(self, user_id: int) -> bool:
        return self.remove_user(user_id)

    def list_all_users(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_admin_registered()
        return _load_users_raw()


auth_mgr = AuthManager()
