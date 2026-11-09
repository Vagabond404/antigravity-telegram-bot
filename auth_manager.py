"""
auth_manager.py - Role-Based Access Control (RBAC), Multi-User & Workspace Isolation
Enhanced for Antigravity Telegram Agent v5.2

Provides:
- User roles: Admin, User (Authorized), Pending, Blocked
- Granular permissions per user (bash, web, subagents, model switching, quotas)
- Fine-grained Isolation vs Shared mode:
    * isolated_memory: own long-term memory vs shared
    * isolated_workspace: dedicated directory on server vs shared
    * isolated_subagents: own subagents vs shared
    * isolated_skills: own skills vs shared
    * isolated_mcp: own MCP servers vs shared
    * sandbox: terminal sandbox enforcement
- Dedicated Secondary Telegram Bot setup & management per user
- Daily turn quota tracking & enforcement
"""

import json
import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import config
from config import BASE_DIR, update_allowed_user

logger = logging.getLogger("auth_manager")

USERS_FILE = BASE_DIR / "users.json"
WORKSPACES_ROOT = BASE_DIR / "workspaces"

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_PENDING = "pending"
ROLE_BLOCKED = "blocked"

ROLES_DESCRIPTION = {
    ROLE_ADMIN: "👑 Administrateur (Contrôle total)",
    ROLE_USER: "👤 Utilisateur Autorisé",
    ROLE_PENDING: "⏳ En attente de validation",
    ROLE_BLOCKED: "🚫 Bloqué",
}

DEFAULT_PERMISSIONS: Dict[str, Any] = {
    "can_use_bash": True,
    "can_use_web": True,
    "can_change_model": False,
    "can_manage_skills": False,
    "can_manage_mcp": False,
    "can_use_subagents": True,
    "can_send_media": True,
    "daily_turns_limit": 0,  # 0 = illimité
    "allowed_models": [],  # [] = tous
}

DEFAULT_ISOLATION: Dict[str, Any] = {
    "mode": "isolated",  # "isolated" ou "shared"
    "isolated_memory": True,
    "isolated_workspace": True,
    "isolated_subagents": False,
    "isolated_skills": False,
    "isolated_mcp": False,
    "workspace_dir": "",
    "sandbox": False,
}

DEFAULT_DEDICATED_BOT: Dict[str, Any] = {
    "enabled": False,
    "token": "",
    "bot_username": "",
    "bot_name": "",
    "status": "stopped",
    "last_error": "",
}

DEFAULT_USAGE: Dict[str, Any] = {
    "total_turns": 0,
    "turns_today": 0,
    "last_turn_date": str(date.today()),
    "total_tokens": 0,
}


def _normalize_user_record(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure every user record has all required fields with defaults."""
    record = dict(data)
    record.setdefault("name", f"User_{uid}")
    record.setdefault("username", "")
    record.setdefault("language", "en")
    record.setdefault("role", ROLE_USER if uid != str(config.ALLOWED_USER_ID or "") else ROLE_ADMIN)
    record.setdefault("created_at", str(date.today()))

    perms = dict(DEFAULT_PERMISSIONS)
    perms.update(record.get("permissions", {}))
    # Admins always have full permissions
    if record["role"] == ROLE_ADMIN:
        for k in perms:
            if isinstance(perms[k], bool):
                perms[k] = True
    record["permissions"] = perms

    iso = dict(DEFAULT_ISOLATION)
    iso.update(record.get("isolation", {}))
    # Every user without exception has their own isolated long-term memory
    iso["isolated_memory"] = True
    if record["role"] == ROLE_ADMIN:
        # Default for admin is shared or root workspace
        iso.setdefault("mode", "shared")
    record["isolation"] = iso

    dbot = dict(DEFAULT_DEDICATED_BOT)
    dbot.update(record.get("dedicated_bot", {}))
    record["dedicated_bot"] = dbot

    usage = dict(DEFAULT_USAGE)
    usage.update(record.get("usage", {}))
    # Reset turns_today if new day
    today_str = str(date.today())
    if usage.get("last_turn_date") != today_str:
        usage["turns_today"] = 0
        usage["last_turn_date"] = today_str
    record["usage"] = usage

    return record


def _load_users_raw() -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Any] = {}
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    data = content
        except Exception as e:
            logger.error(f"Error reading {USERS_FILE}: {e}")

    # Ensure primary admin is seeded
    if config.ALLOWED_USER_ID:
        uid = str(config.ALLOWED_USER_ID)
        if uid not in data:
            data[uid] = {
                "name": "Administrateur Principal",
                "username": "",
                "role": ROLE_ADMIN,
                "created_at": str(date.today()),
            }

    # Normalize all records
    normalized: Dict[str, Dict[str, Any]] = {}
    for uid, u in data.items():
        normalized[str(uid)] = _normalize_user_record(str(uid), u)

    return normalized


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
                users[uid] = _normalize_user_record(uid, {
                    "name": users.get(uid, {}).get("name", "Administrateur"),
                    "username": users.get(uid, {}).get("username", ""),
                    "role": ROLE_ADMIN,
                    "created_at": users.get(uid, {}).get("created_at", str(date.today())),
                })
                _save_users_raw(users)

    def has_any_admin(self) -> bool:
        if config.ALLOWED_USER_ID:
            return True
        users = _load_users_raw()
        return any(u.get("role") == ROLE_ADMIN for u in users.values())

    def claim_initial_admin(self, user_id: int, name: str = "", username: str = "") -> bool:
        if self.has_any_admin():
            return False
        update_allowed_user(user_id)
        return self.add_user(
            user_id=user_id,
            name=name or "Administrateur",
            username=username or "",
            role=ROLE_ADMIN,
        )

    def get_primary_admin_id(self) -> Optional[int]:
        if config.ALLOWED_USER_ID:
            try:
                return int(config.ALLOWED_USER_ID)
            except (ValueError, TypeError):
                pass
        users = _load_users_raw()
        for uid, u in users.items():
            if u.get("role") == ROLE_ADMIN and str(uid).isdigit():
                return int(uid)
        return None

    def get_all_admin_ids(self) -> List[int]:
        """Return all registered administrator Telegram IDs."""
        self._ensure_admin_registered()
        users = _load_users_raw()
        admins = set()
        if config.ALLOWED_USER_ID:
            try:
                admins.add(int(config.ALLOWED_USER_ID))
            except (ValueError, TypeError):
                pass
        for uid, u in users.items():
            if u.get("role") == ROLE_ADMIN and str(uid).lstrip("-").isdigit():
                try:
                    admins.add(int(uid))
                except Exception:
                    pass
        return list(admins)

    def update_user(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Update arbitrary user fields safely with normalization."""
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            users[uid] = _normalize_user_record(uid, updates)
        else:
            users[uid].update(updates)
            users[uid] = _normalize_user_record(uid, users[uid])
        return _save_users_raw(users)

    def update_user_name_or_username(
        self, user_id: int, name: Optional[str] = None, username: Optional[str] = None
    ) -> bool:
        """Update display name and/or @username for a user."""
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            users[uid] = _normalize_user_record(uid, {})
        if name is not None and name.strip():
            users[uid]["name"] = name.strip()
        if username is not None:
            users[uid]["username"] = username.strip().lstrip("@")
        return _save_users_raw(users)

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

    def is_authorized(self, user_id: int) -> bool:
        """True if user is either Admin or Authorized User."""
        role = self.get_user_role(user_id)
        return role in (ROLE_ADMIN, ROLE_USER)

    def is_blocked(self, user_id: int) -> bool:
        return self.get_user_role(user_id) == ROLE_BLOCKED

    def can_user_do(self, user_id: int, permission_name: str) -> bool:
        """Check a specific permission flag for a user."""
        if self.is_admin(user_id):
            return True
        user = self.get_user(user_id)
        if not user or user.get("role") != ROLE_USER:
            return False
        perms = user.get("permissions", {})
        return bool(perms.get(permission_name, DEFAULT_PERMISSIONS.get(permission_name, False)))

    def register_access_request(self, user_id: int, name: str, username: str = "") -> Tuple[bool, str]:
        users = _load_users_raw()
        uid = str(user_id)
        if uid in users:
            current_role = users[uid].get("role")
            if current_role == ROLE_BLOCKED:
                return (False, "blocked")
            if current_role in (ROLE_ADMIN, ROLE_USER):
                return (True, current_role)

        users[uid] = _normalize_user_record(uid, {
            "name": name or f"User_{uid}",
            "username": username or "",
            "role": ROLE_PENDING,
            "created_at": str(date.today()),
        })
        _save_users_raw(users)
        return (True, ROLE_PENDING)

    def add_user(
        self,
        user_id: int,
        name: str = "",
        username: str = "",
        role: str = ROLE_USER,
        permissions: Optional[Dict[str, Any]] = None,
        isolation: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add or update an authorized user."""
        users = _load_users_raw()
        uid = str(user_id)

        rec = users.get(uid, {})
        rec["name"] = name or rec.get("name") or f"User_{uid}"
        rec["username"] = username or rec.get("username", "")
        rec["role"] = role
        rec["created_at"] = rec.get("created_at", str(date.today()))

        if permissions:
            perms = dict(rec.get("permissions", DEFAULT_PERMISSIONS))
            perms.update(permissions)
            rec["permissions"] = perms

        if isolation:
            iso = dict(rec.get("isolation", DEFAULT_ISOLATION))
            iso.update(isolation)
            rec["isolation"] = iso

        users[uid] = _normalize_user_record(uid, rec)
        ok = _save_users_raw(users)
        if ok and role in (ROLE_ADMIN, ROLE_USER):
            # Pre-create workspace if needed
            self.get_user_workspace(user_id)
        return ok

    def set_user_role(self, user_id: int, role: str) -> bool:
        users = _load_users_raw()
        uid = str(user_id)

        if config.ALLOWED_USER_ID and uid == str(config.ALLOWED_USER_ID) and role != ROLE_ADMIN:
            logger.warning("Attempted to demote master admin!")
            return False

        if uid not in users:
            users[uid] = _normalize_user_record(uid, {
                "name": f"User_{uid}",
                "role": role,
            })
        else:
            users[uid]["role"] = role

        ok = _save_users_raw(users)
        if ok and role in (ROLE_ADMIN, ROLE_USER):
            self.get_user_workspace(user_id)
        return ok

    def toggle_user_permission(self, user_id: int, perm_key: str) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        perms = users[uid].setdefault("permissions", dict(DEFAULT_PERMISSIONS))
        current = bool(perms.get(perm_key, DEFAULT_PERMISSIONS.get(perm_key, False)))
        perms[perm_key] = not current
        return _save_users_raw(users)

    def set_daily_turns_limit(self, user_id: int, limit: int) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        perms = users[uid].setdefault("permissions", dict(DEFAULT_PERMISSIONS))
        perms["daily_turns_limit"] = max(0, int(limit))
        return _save_users_raw(users)

    def toggle_user_isolation_flag(self, user_id: int, flag_key: str) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        iso = users[uid].setdefault("isolation", dict(DEFAULT_ISOLATION))
        current = bool(iso.get(flag_key, DEFAULT_ISOLATION.get(flag_key, False)))
        iso[flag_key] = not current
        ok = _save_users_raw(users)
        if ok:
            self.get_user_workspace(user_id)
        return ok

    def set_isolation_mode(self, user_id: int, mode: str) -> bool:
        """Preset in one click: 'isolated' (all isolated) or 'shared' (all shared)."""
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        iso = users[uid].setdefault("isolation", dict(DEFAULT_ISOLATION))
        iso["mode"] = mode
        if mode == "isolated":
            iso["isolated_memory"] = True
            iso["isolated_workspace"] = True
            iso["isolated_subagents"] = True
            iso["isolated_skills"] = True
            iso["isolated_mcp"] = True
            iso["sandbox"] = False
        else:  # shared
            iso["isolated_memory"] = False
            iso["isolated_workspace"] = False
            iso["isolated_subagents"] = False
            iso["isolated_skills"] = False
            iso["isolated_mcp"] = False
            iso["sandbox"] = False
        ok = _save_users_raw(users)
        if ok:
            self.get_user_workspace(user_id)
        return ok

    def set_dedicated_bot(
        self,
        user_id: int,
        token: str,
        bot_username: str = "",
        bot_name: str = "",
        enabled: bool = True,
    ) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        dbot = users[uid].setdefault("dedicated_bot", dict(DEFAULT_DEDICATED_BOT))
        dbot["token"] = token.strip()
        dbot["bot_username"] = bot_username.strip()
        dbot["bot_name"] = bot_name.strip()
        dbot["enabled"] = bool(enabled and token.strip())
        dbot["status"] = "configured" if dbot["enabled"] else "stopped"
        dbot["last_error"] = ""
        return _save_users_raw(users)

    def toggle_dedicated_bot(self, user_id: int, enabled: bool) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        dbot = users[uid].setdefault("dedicated_bot", dict(DEFAULT_DEDICATED_BOT))
        dbot["enabled"] = bool(enabled)
        dbot["status"] = "stopped" if not enabled else "configured"
        return _save_users_raw(users)

    def remove_dedicated_bot(self, user_id: int) -> bool:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return False
        users[uid]["dedicated_bot"] = dict(DEFAULT_DEDICATED_BOT)
        return _save_users_raw(users)

    def get_user_workspace(self, user_id: int) -> Path:
        """
        Get or initialize the workspace directory for this user.
        If user has isolated_workspace, returns BASE_DIR / workspaces / user_<uid>.
        Otherwise returns global config.WORKSPACE_DIR.
        """
        user = self.get_user(user_id)
        if not user or user.get("role") == ROLE_ADMIN:
            # Check if admin has custom isolated workspace or uses default
            iso = user.get("isolation", {}) if user else {}
            if not iso.get("isolated_workspace", False):
                return config.WORKSPACE_DIR

        iso = user.get("isolation", {}) if user else {}
        if not iso.get("isolated_workspace", True):
            return config.WORKSPACE_DIR

        custom_dir = iso.get("workspace_dir", "").strip()
        if custom_dir:
            ws_path = Path(custom_dir).resolve()
        else:
            ws_path = (WORKSPACES_ROOT / f"user_{user_id}").resolve()

        try:
            ws_path.mkdir(parents=True, exist_ok=True)
            # Ensure subfolders if subagents or skills are isolated
            if iso.get("isolated_subagents"):
                (ws_path / ".agents" / "agents").mkdir(parents=True, exist_ok=True)
            if iso.get("isolated_skills"):
                user_skills_dir = ws_path / ".agents" / "skills"
                user_skills_dir.mkdir(parents=True, exist_ok=True)
                # Link or copy master mastery skill if missing
                master_skill = BASE_DIR / ".agents" / "skills" / "telegram-bot-mastery"
                user_master_skill = user_skills_dir / "telegram-bot-mastery"
                if master_skill.exists() and not user_master_skill.exists():
                    try:
                        shutil.copytree(str(master_skill), str(user_master_skill))
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error initializing user workspace {ws_path}: {e}")
            return config.WORKSPACE_DIR

        return ws_path

    def check_daily_quota(self, user_id: int) -> Tuple[bool, str]:
        """Verify if user has remaining turns today."""
        if self.is_admin(user_id):
            return True, ""
        user = self.get_user(user_id)
        if not user:
            return False, "Utilisateur introuvable."
        perms = user.get("permissions", {})
        limit = perms.get("daily_turns_limit", 0)
        if not limit or limit <= 0:
            return True, ""  # Illimité

        usage = user.get("usage", {})
        today_str = str(date.today())
        turns_today = usage.get("turns_today", 0) if usage.get("last_turn_date") == today_str else 0
        if turns_today >= limit:
            return False, f"Quota quotidien atteint ({turns_today}/{limit} requêtes aujourd'hui). Réinitialisation à minuit."
        return True, ""

    def record_turn_usage(self, user_id: int, tokens: int = 0) -> None:
        users = _load_users_raw()
        uid = str(user_id)
        if uid not in users:
            return
        usage = users[uid].setdefault("usage", dict(DEFAULT_USAGE))
        today_str = str(date.today())
        if usage.get("last_turn_date") != today_str:
            usage["turns_today"] = 1
            usage["last_turn_date"] = today_str
        else:
            usage["turns_today"] = int(usage.get("turns_today", 0)) + 1
        usage["total_turns"] = int(usage.get("total_turns", 0)) + 1
        usage["total_tokens"] = int(usage.get("total_tokens", 0)) + int(tokens)
        _save_users_raw(users)

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
