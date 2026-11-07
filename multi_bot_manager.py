"""
multi_bot_manager.py - Secondary Dedicated Telegram Bots Engine
Enhanced for Antigravity Telegram Agent v5.2

Allows the Administrator to assign a dedicated secondary Telegram Bot (via @BotFather token)
to any user.
The dedicated bot runs in its own background polling loop, authenticates exclusively
the assigned user, and executes turns inside the user's isolated workspace and memory partition.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, Callable
import requests
from telegram import Update, constants
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from auth_manager import auth_mgr, ROLE_ADMIN, ROLE_USER
from i18n import get_user_language

logger = logging.getLogger("multi_bot_manager")


async def validate_bot_token(token: str) -> Tuple[bool, str, str]:
    """
    Validate a Telegram Bot Token via the Telegram Bot API.
    Returns: (is_valid, bot_username, bot_name_or_error)
    """
    if not token or not token.strip():
        return False, "", "Empty bot token."
    cleaned = token.strip()
    url = f"https://api.telegram.org/bot{cleaned}/getMe"
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        data = resp.json()
        if data.get("ok"):
            res = data.get("result", {})
            username = res.get("username", "")
            first_name = res.get("first_name", "")
            return True, username, first_name
        else:
            desc = data.get("description", "Invalid token.")
            return False, "", desc
    except Exception as e:
        return False, "", f"Erreur de connexion Telegram: {e}"


class MultiBotManager:
    """Manages dedicated secondary Telegram bots."""

    def __init__(self):
        self._running_apps: Dict[str, Application] = {}
        self._turn_callback: Optional[Callable] = None
        self._lock = asyncio.Lock()

    def set_turn_callback(self, callback: Callable) -> None:
        self._turn_callback = callback

    def is_bot_running(self, user_id: int) -> bool:
        return str(user_id) in self._running_apps

    async def start_dedicated_bot(
        self,
        user_id: int,
        token: str,
        turn_callback: Optional[Callable] = None,
    ) -> Tuple[bool, str]:
        """Start or restart a secondary bot for a user."""
        async with self._lock:
            uid_str = str(user_id)
            cb = turn_callback or self._turn_callback
            if not cb:
                return False, "Callback d'exécution non configuré."

            # Stop existing instance if already running
            if uid_str in self._running_apps:
                await self._stop_bot_internal(uid_str)

            # Validate token
            is_valid, bot_username, bot_name = await validate_bot_token(token)
            if not is_valid:
                auth_mgr.set_dedicated_bot(user_id, token, enabled=False)
                return False, f"Token invalide: {bot_name}"

            try:
                logger.info(f"Building secondary Telegram Bot @{bot_username} for user {user_id}...")
                app = ApplicationBuilder().token(token.strip()).build()

                # Register handlers for the secondary bot
                self._register_secondary_handlers(app, user_id, token.strip(), cb)

                await app.initialize()
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)

                self._running_apps[uid_str] = app
                auth_mgr.set_dedicated_bot(
                    user_id=user_id,
                    token=token.strip(),
                    bot_username=bot_username,
                    bot_name=bot_name,
                    enabled=True,
                )
                logger.info(f"Secondary Telegram Bot @{bot_username} successfully started for user {user_id}!")
                return True, f"@{bot_username}"
            except Exception as e:
                logger.error(f"Failed to start secondary bot for user {user_id}: {e}", exc_info=True)
                return False, str(e)

    async def _stop_bot_internal(self, uid_str: str) -> bool:
        app = self._running_apps.pop(uid_str, None)
        if not app:
            return False
        try:
            logger.info(f"Stopping secondary Telegram bot for user {uid_str}...")
            if app.updater and app.updater.running:
                await app.updater.stop()
            if app.running:
                await app.stop()
            await app.shutdown()
            return True
        except Exception as e:
            logger.warning(f"Error during secondary bot shutdown for {uid_str}: {e}")
            return False

    async def stop_dedicated_bot(self, user_id: int) -> bool:
        async with self._lock:
            ok = await self._stop_bot_internal(str(user_id))
            auth_mgr.toggle_dedicated_bot(user_id, enabled=False)
            return ok

    async def restart_dedicated_bot(self, user_id: int, turn_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        user = auth_mgr.get_user(user_id)
        if not user:
            return False, "User not found."
        token = user.get("dedicated_bot", {}).get("token", "")
        if not token:
            return False, "No token configured for this user."
        return await self.start_dedicated_bot(user_id, token, turn_callback=turn_callback)

    async def start_all_enabled_bots(self, turn_callback: Callable) -> int:
        """Start all secondary bots that have enabled=True on startup."""
        self._turn_callback = turn_callback
        users = auth_mgr.list_all_users()
        started_count = 0
        for uid_str, u in users.items():
            dbot = u.get("dedicated_bot", {})
            if dbot.get("enabled") and dbot.get("token") and u.get("role") in (ROLE_ADMIN, ROLE_USER):
                try:
                    uid = int(uid_str)
                    ok, res = await self.start_dedicated_bot(uid, dbot["token"], turn_callback=turn_callback)
                    if ok:
                        started_count += 1
                        logger.info(f"Restored dedicated bot {res} for user {uid}")
                    else:
                        logger.warning(f"Could not restore dedicated bot for user {uid}: {res}")
                except Exception as e:
                    logger.error(f"Error restoring dedicated bot for {uid_str}: {e}")
        return started_count

    async def stop_all_bots(self) -> None:
        async with self._lock:
            for uid_str in list(self._running_apps.keys()):
                await self._stop_bot_internal(uid_str)

    def _register_secondary_handlers(
        self,
        app: Application,
        owner_id: int,
        bot_token: str,
        turn_callback: Callable,
    ) -> None:
        """Set up standard handlers on the secondary bot with strict owner access control."""

        async def _check_access(update: Update) -> bool:
            user = update.effective_user
            if not user:
                return False
            # Only owner and master admins can use this bot
            if user.id == owner_id or auth_mgr.is_admin(user.id):
                return True
            if update.message:
                try:
                    user_lang = get_user_language(user.id)
                    if user_lang == "fr":
                        denied_msg = "🛡️ <b>Accès Refusé :</b> Ce bot Antigravity est une instance dédiée et privée, réservée exclusivement à son propriétaire."
                    else:
                        denied_msg = "🛡️ <b>Access Denied:</b> This dedicated Antigravity bot is private and reserved exclusively for its assigned owner."
                    await update.message.reply_text(
                        denied_msg,
                        parse_mode=constants.ParseMode.HTML,
                    )
                except Exception:
                    pass
            return False

        async def _sec_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await _check_access(update):
                return
            u_info = auth_mgr.get_user(owner_id) or {}
            user_lang = get_user_language(owner_id)
            if user_lang == "fr":
                name = u_info.get("name", "Utilisateur")
                msg = (
                    f"👋 <b>Bonjour {name} !</b>\n\n"
                    "Bienvenue sur votre <b>Bot Antigravity Dédié</b>.\n"
                    "Cet espace fonctionne sur une partition isolée du serveur avec votre propre mémoire, "
                    "votre espace de travail et vos sous-agents dédiés.\n\n"
                    "💬 <i>Envoyez-moi simplement votre demande, un document ou une photo pour commencer !</i>"
                )
            else:
                name = u_info.get("name", "User")
                msg = (
                    f"👋 <b>Hello {name}!</b>\n\n"
                    "Welcome to your <b>Dedicated Antigravity Bot</b>.\n"
                    "This instance runs on an isolated server partition with your own long-term memory, "
                    "isolated workspace, and dedicated subagents.\n\n"
                    "💬 <i>Send me your prompt, document, or photo to get started!</i>"
                )
            await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

        async def _sec_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await _check_access(update):
                return
            text = (update.message.text or "").strip()
            if not text:
                return
            await turn_callback(
                update=update,
                context=context,
                prompt=text,
                user_id=owner_id,
                bot_token=bot_token,
            )

        async def _sec_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await _check_access(update):
                return
            caption = (update.message.caption or "").strip()
            user_lang = get_user_language(owner_id)
            default_prompt = "Analyse ce média et réponds à ma demande." if user_lang == "fr" else "Analyze this media and fulfill my request."
            prompt = caption or default_prompt
            await turn_callback(
                update=update,
                context=context,
                prompt=prompt,
                user_id=owner_id,
                bot_token=bot_token,
            )

        app.add_handler(CommandHandler("start", _sec_start))
        app.add_handler(CommandHandler("help", _sec_start))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO | filters.VIDEO, _sec_media))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _sec_prompt))


multi_bot_mgr = MultiBotManager()
