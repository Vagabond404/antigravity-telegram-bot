"""
bot.py - Antigravity Universal Telegram Gateway (v4.0 - Full CLI & Multi-Agent Edition)
- 100% compatible with the latest Antigravity CLI (`agy`) on Windows, Linux, and macOS
- Dynamic models (`agy models`), reasoning efforts (`low|medium|high|xhigh|max|auto`), modes, and `--sandbox`
- Multi-Agent & Subagent orchestration (`invoke_subagent`, `define_subagent`, live subagent stream)
- Full bidirectional multimedia (Photos, Videos, Audio, Voice, Animations, Documents, Archives)
- Interactive Telegram Control Center (`/settings`, `/models`, `/mcp`, `/plugins`, `/remote`, `/sessions`)
- Persistent vector memory (Mem0) across all conversations
- Zero hardcoded personal information — ready for public GitHub deployment
"""

import asyncio
import logging
import os
import re
import sys
import json
import html
from pathlib import Path
from typing import Optional, Dict, Any, List

from telegram import Update, constants, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

import config
from config import (
    BASE_DIR,
    TEMP_DIR,
    SETTINGS_FILE,
    DEFAULT_SETTINGS,
    TRANSIENT_MSGS_FILE,
    TURN_SENT_FILES_FILE,
    IS_WINDOWS,
    load_settings,
    save_settings,
    load_conversations,
    find_agy_binary,
)
from command_manager import command_mgr
from agent_runner import (
    AgentRunner,
    fetch_available_models,
    fetch_available_agents,
    list_mcp_servers,
    toggle_mcp_server,
    install_recommended_mcp_server,
    list_cli_plugins,
    run_plugin_action,
    manage_remote_control,
    update_cli_binary,
    run_agy_subcommand,
)
from server_watchdog import check_and_heal_services, restart_service
from log_scanner import log_scanner
from auth_manager import (
    auth_mgr,
    ROLE_ADMIN,
    ROLE_PENDING,
    ROLE_BLOCKED,
    ROLES_DESCRIPTION,
)
from ui_helpers import (
    md_to_html,
    smart_split_html,
    format_tool_call_html,
    sanitize_telegram_html,
    strip_all_html,
    truncate_telegram_html,
    format_settings_summary_html,
    get_settings_keyboard,
    get_mode_selection_keyboard,
    get_model_selection_keyboard,
    get_effort_selection_keyboard,
    get_timeout_selection_keyboard,
    get_verbosity_selection_keyboard,
    get_agents_keyboard,
    get_mcp_keyboard,
    get_mcp_catalog_keyboard,
    get_plugins_keyboard,
    get_remote_control_keyboard,
    get_sessions_keyboard,
    get_workspace_keyboard,
    get_persona_keyboard,
    format_update_check_html,
    get_update_prompt_keyboard,
)
from memory_manager import (
    add_or_update_memory,
    delete_memory,
    get_summary_html,
    search_memories,
    seed_default_memories,
)
from updater import (
    PENDING_UPDATE_ACK_FILE,
    check_for_updates,
    should_notify_for_commit,
    mark_commit_notified,
    mark_commit_dismissed,
    perform_safe_update,
    spawn_detached_restarter,
    load_local_version_manifest,
)

h = html.escape

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("antigravity_bot")

PM = constants.ParseMode.HTML

_SPINNER_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
_spinner_idx = 0

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".aac"}
VOICE_EXTS = {".ogg", ".opus"}
ANIM_EXTS = {".gif"}


def _next_spinner() -> str:
    global _spinner_idx
    frame = _SPINNER_FRAMES[_spinner_idx % len(_SPINNER_FRAMES)]
    _spinner_idx += 1
    return frame


async def safe_edit_message(
    msg,
    text: str,
    parse_mode=PM,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    if not msg or not text:
        return False

    display = truncate_telegram_html(text, max_length=4000)

    try:
        await msg.edit_text(display, parse_mode=parse_mode, reply_markup=reply_markup)
        return True
    except RetryAfter as ra:
        await asyncio.sleep(min(float(ra.retry_after), 5.0))
        return False
    except Exception as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        if "can't parse" not in err_str and "bad request" not in err_str and "entities" not in err_str:
            logger.debug(f"edit_text non-HTML warning: {e}")
            return False

    sanitised = sanitize_telegram_html(display)
    try:
        await msg.edit_text(sanitised, parse_mode=parse_mode, reply_markup=reply_markup)
        return True
    except Exception:
        pass

    plain = strip_all_html(display)[:4000]
    try:
        await msg.edit_text(plain, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"Plain text edit_text failed: {e}")
        return False


async def safe_reply_message(
    update_or_msg,
    text: str,
    parse_mode=PM,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> object:
    display = truncate_telegram_html(text, max_length=4000)
    send_fn = getattr(update_or_msg, "reply_text", None) or getattr(
        getattr(update_or_msg, "message", None), "reply_text", None
    )
    if not send_fn:
        return None

    try:
        return await send_fn(display, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        err_str = str(e).lower()
        if "can't parse" in err_str or "bad request" in err_str or "entities" in err_str:
            sanitised = sanitize_telegram_html(display)
            try:
                return await send_fn(sanitised, parse_mode=parse_mode, reply_markup=reply_markup)
            except Exception:
                pass
        plain = strip_all_html(display)[:4000]
        try:
            return await send_fn(plain, reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Plain text reply failed: {e2}")
            return None


runner = AgentRunner()
settings = load_settings()

# Interactive input state for admin settings (e.g. changing workspace, adding MCP, etc.)
pending_admin_input: Dict[int, str] = {}

# Turn execution lock & queue so concurrent messages or albums never collide or drop
turn_execution_lock = asyncio.Lock()


def ensure_first_admin_if_needed(user) -> bool:
    """
    If no administrator has been registered yet on a fresh installation,
    automatically claims Admin status for the first Telegram user who messages the bot.
    """
    if not user:
        return False
    if not auth_mgr.has_any_admin():
        name = user.first_name or "Administrateur"
        username = user.username or ""
        auth_mgr.claim_initial_admin(user.id, name=name, username=username)
        logger.info(f"First-time onboarding: Registered {name} (ID={user.id}) as primary Administrator!")
        return True
    return False


def is_admin(user_id: int, user_obj=None) -> bool:
    if user_obj:
        ensure_first_admin_if_needed(user_obj)
    return auth_mgr.is_admin(user_id)


def _get_users_dashboard_keyboard() -> InlineKeyboardMarkup:
    users = auth_mgr.list_all_users()
    rows = []
    for uid, u in users.items():
        role = u.get("role", ROLE_BLOCKED)
        role_icon = "👑" if role == ROLE_ADMIN else ("⏳" if role == ROLE_PENDING else "🚫")
        name = u.get("name") or f"ID:{uid}"
        btn_text = f"{role_icon} {name[:18]} ({role})"
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"auth:view:{uid}")])

    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data="auth:refresh"),
        InlineKeyboardButton("⬅️ Paramètres", callback_data="menu_main"),
    ])
    rows.append([InlineKeyboardButton("❌ Fermer", callback_data="close_menu")])
    return InlineKeyboardMarkup(rows)


def _get_user_detail_keyboard(target_uid: str) -> InlineKeyboardMarkup:
    u = auth_mgr.get_user(int(target_uid)) or {}
    role = u.get("role", ROLE_BLOCKED)
    primary_id = auth_mgr.get_primary_admin_id()
    is_master = bool(primary_id and str(target_uid) == str(primary_id))

    rows = []
    if not is_master:
        if role != ROLE_ADMIN:
            rows.append([
                InlineKeyboardButton("👑 Définir : Administrateur", callback_data=f"auth:role:{target_uid}:{ROLE_ADMIN}")
            ])
        if role != ROLE_BLOCKED:
            rows.append([
                InlineKeyboardButton("🚫 Bloquer l'utilisateur", callback_data=f"auth:role:{target_uid}:{ROLE_BLOCKED}")
            ])
        rows.append([InlineKeyboardButton("🗑️ Retirer de la liste", callback_data=f"auth:delete:{target_uid}")])

    rows.append([InlineKeyboardButton("⬅️ Retour à la liste", callback_data="auth:refresh")])
    return InlineKeyboardMarkup(rows)


async def sync_telegram_commands(bot) -> None:
    try:
        cmds = command_mgr.get_all_telegram_commands()
        await bot.set_my_commands(cmds)
        logger.info(f"Synchronized {len(cmds)} commands with Telegram Bot API.")
    except Exception as e:
        logger.error(f"Failed to synchronize commands with Telegram: {e}")


async def post_init(application) -> None:
    logger.info("Exécution du post_init (Initialisation Mem0, Modèles CLI et Services)...")

    import socket
    for _ in range(10):
        try:
            await asyncio.get_event_loop().run_in_executor(None, socket.gethostbyname, "api.telegram.org")
            break
        except Exception:
            await asyncio.sleep(1.5)

    try:
        seed_default_memories()
        config.ensure_default_skill_installed()
    except Exception as e:
        logger.warning(f"Non-fatal init warning (memory/skill): {e}")

    # Pre-fetch available models from `agy models`
    try:
        models = await fetch_available_models(force_refresh=True)
        if models:
            model_ids = [m[0] for m in models]
            if settings.get("model") not in model_ids:
                settings["model"] = model_ids[0]
                save_settings(settings)
            logger.info(f"Loaded {len(models)} models from Antigravity CLI. Active: {settings.get('model')}")
    except Exception as e:
        logger.warning(f"Could not pre-fetch models from CLI: {e}")

    await sync_telegram_commands(application.bot)

    admin_id = auth_mgr.get_primary_admin_id()
    just_completed_update = False

    # Check if we just restarted after an autonomous self-update
    if PENDING_UPDATE_ACK_FILE.is_file():
        try:
            ack_data = json.loads(PENDING_UPDATE_ACK_FILE.read_text(encoding="utf-8"))
            PENDING_UPDATE_ACK_FILE.unlink(missing_ok=True)
            just_completed_update = True
            ack_chat = ack_data.get("chat_id") or admin_id
            ack_msg_id = ack_data.get("message_id")
            bot_ver = ack_data.get("bot_version", "4.1.0")
            old_sha = ack_data.get("old_sha", "")
            new_sha = ack_data.get("new_sha", "")
            agy_ver = ack_data.get("agy_version", "")
            done_text = (
                "✅ <b>Mise à Jour Terminée &amp; Système Redémarré avec Succès !</b>\n\n"
                f"• 📦 <b>Version du Bot :</b> <code>v{h(bot_ver)}</code> (<code>{h(old_sha)}</code> ➔ <code>{h(new_sha)}</code>)\n"
                f"• ⚡ <b>Antigravity CLI :</b> <code>v{h(agy_ver)}</code> (Compatible ✅)\n"
                f"• 🧠 <b>Modèle actif :</b> <code>{h(settings.get('model', ''))}</code>\n"
                "• 🛡️ <b>Données, Mémoire Mem0, Sessions &amp; Skills :</b> 100% préservés !"
            )
            if ack_chat and ack_msg_id:
                try:
                    await application.bot.edit_message_text(
                        chat_id=ack_chat,
                        message_id=ack_msg_id,
                        text=done_text,
                        parse_mode=PM,
                    )
                except Exception:
                    await application.bot.send_message(chat_id=ack_chat, text=done_text, parse_mode=PM)
            elif ack_chat:
                await application.bot.send_message(chat_id=ack_chat, text=done_text, parse_mode=PM)
        except Exception as e:
            logger.warning(f"Failed processing post-update ACK: {e}")

    if admin_id and not just_completed_update:
        try:
            _, report_html, has_healed = await check_and_heal_services(auto_heal=True)
            agent_name = settings.get("agent_name", "Antigravity Agent")
            ver_info = load_local_version_manifest()
            heal_notice = "\n<i>(Services relancés automatiquement)</i>" if has_healed else ""
            boot_msg = (
                f"🟢 <b>{h(agent_name)} (v{h(ver_info.get('bot_version', '4.1.0'))}) est en ligne !</b>{heal_notice}\n\n"
                f"{report_html}\n\n"
                f"• 🧠 <b>Modèle actif :</b> <code>{h(settings.get('model', ''))}</code>\n"
                f"• 🎛️ <i>Tapez /settings pour le Centre de Contrôle, /update pour vérifier les mises à jour ou /help.</i>"
            )
            await application.bot.send_message(chat_id=admin_id, text=boot_msg, parse_mode=PM)
        except Exception as be:
            logger.debug(f"Could not send boot notification: {be}")

    async def _on_auto_heal_alert(s_key: str, s_name: str, err_txt: str):
        await trigger_auto_heal_agent(s_key, s_name, err_txt, application)

    log_scanner.register_dispatch_callback(_on_auto_heal_alert)
    if not IS_WINDOWS:
        asyncio.create_task(auto_heal_background_worker())
    asyncio.create_task(auto_update_watcher_worker(application))


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global exception handler so network glitches or API errors never crash the bot."""
    err = context.error
    if isinstance(err, (TimedOut, NetworkError, RetryAfter)):
        logger.warning(f"Transient Telegram network/rate error handled: {err}")
        return
    logger.error(f"Unhandled exception in update handler: {err}", exc_info=context.error)


# =============================================================================
# Command Handlers
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    first_name = user.first_name or "Ami"
    just_claimed = ensure_first_admin_if_needed(user)

    if is_admin(uid):
        agent_name = settings.get("agent_name", "Antigravity Agent")
        claim_banner = (
            "🎉 <b>Configuration Initiale Réussie !</b>\n"
            f"Votre compte (<code>{uid}</code>) a été enregistré comme <b>Administrateur Principal</b>.\n\n"
            if just_claimed
            else ""
        )
        welcome = (
            f"{claim_banner}"
            f"👋 <b>Bienvenue sur {h(agent_name)} (Antigravity CLI v4.0) !</b>\n\n"
            "Votre passerelle IA autonome universelle (Windows & Linux) propulsée par la dernière version de <b>Google Antigravity CLI</b>.\n\n"
            "⚡ <b>Capacités Intégrées :</b>\n"
            "• 🧠 <b>Modèles & Effort Dynamiques :</b> Sélection en direct depuis <code>agy models</code> et effort jusqu'à <code>xhigh</code> / <code>max</code> (<code>/settings</code>, <code>/models</code>).\n"
            "• 🤝 <b>Multi-Agents & Sous-Agents :</b> Orchestration parallèle de sous-agents autonomes (<code>/agents</code>, <code>/teamwork</code>).\n"
            "• 📤 <b>Multimédia Bidirectionnel :</b> Envoyez et recevez images, vidéos, audios, notes vocales, PDF et archives sans limite.\n"
            "• 🔌 <b>Écosystème CLI Complet :</b> Gérez vos serveurs <code>/mcp</code>, <code>/plugins</code>, <code>/remote</code> et <code>/sessions</code> en un clic.\n"
            "• 🧠 <b>Mémoire Long-Terme Inter-Conversations :</b> Mémoire vectorielle locale Mem0 (<code>/memory</code>, <code>/remember</code>, <code>/forget</code>).\n\n"
            "💡 <i>Envoyez un message, une photo, un fichier ou tapez <code>/settings</code> pour tout personnaliser !</i>"
        )
        await update.message.reply_text(
            welcome,
            reply_markup=get_settings_keyboard(settings),
            parse_mode=PM,
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📨 Demander un accès à l'Administrateur", callback_data="guest_req:ask")]
        ])
        await update.message.reply_text(
            f"👋 Bonjour {h(first_name)} !\n\n"
            "🔒 Ce bot Antigravity est privé. Cliquez ci-dessous si vous souhaitez demander une autorisation d'accès :",
            reply_markup=kb,
            parse_mode=PM,
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Accès réservé à l'administrateur.")
        return

    help_text = (
        "📚 <b>Guide Complet — Antigravity Telegram Agent</b>\n\n"
        "<b>🎛️ Contrôle & Configuration Antigravity CLI :</b>\n"
        "• <code>/settings</code> : Centre de contrôle interactif complet\n"
        "• <code>/models</code> : Choisir le modèle IA en direct (<code>agy models</code>)\n"
        "• <code>/effort</code> : Régler la réflexion (<code>auto</code>, <code>low</code>, <code>medium</code>, <code>high</code>, <code>xhigh</code>, <code>max</code>)\n"
        "• <code>/mode</code> : Mode d'exécution (<code>auto-approve</code>, <code>accept-edits</code>, <code>plan</code>)\n"
        "• <code>/agents</code> : Configurer le mode Multi-Agents & les profils d'agents\n"
        "• <code>/mcp</code> : Activer/désactiver ou ajouter des serveurs MCP\n"
        "• <code>/plugins</code> : Gérer et importer les plugins Antigravity CLI\n"
        "• <code>/remote</code> : Démarrer/arrêter le démon Remote Control\n"
        "• <code>/workspace</code> : Changer le dossier de travail actif\n"
        "• <code>/update_cli</code> : Mettre à jour le binaire <code>agy</code>\n\n"
        "<b>💬 Sessions & Exécution :</b>\n"
        "• <code>/status</code> : État système, version CLI, RAM/CPU et tokens utilisés\n"
        "• <code>/sessions</code> : Reprendre une conversation précédente ou en créer une\n"
        "• <code>/clear</code> : Réinitialiser la session en cours\n"
        "• <code>/abort</code> : Stopper immédiatement l'exécution en cours\n\n"
        "<b>🚀 Workflows Spéciaux & Multi-Agents :</b>\n"
        "• <code>/goal &lt;objectif&gt;</code> : Exécution autonome longue durée jusqu'à 100%\n"
        "• <code>/teamwork &lt;mission&gt;</code> : Déployer une équipe de sous-agents en parallèle\n"
        "• <code>/boost &lt;problème&gt;</code> : Réflexion maximale (<code>max</code>) multi-perspectives\n"
        "• <code>/plan &lt;sujet&gt;</code> : Planification architecturale détaillée\n"
        "• <code>/grill_me &lt;projet&gt;</code> : Entretien interactif de conception\n"
        "• <code>/commands</code> : Créer vos propres commandes Telegram sur mesure\n\n"
        "<b>🧠 Mémoire Long-Terme :</b>\n"
        "• <code>/memory</code>, <code>/remember</code>, <code>/forget</code> : Mémoire vectorielle Mem0 (Profil, Préférences, Projets)"
    )
    await update.message.reply_text(help_text, parse_mode=PM)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return

    import psutil
    try:
        mem_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        mem_mb = 0.0

    agy_bin = find_agy_binary()
    agy_status = f"✅ <code>{h(agy_bin)}</code>" if agy_bin else "❌ Introuvable"

    running_str = "🟢 En cours d'exécution" if runner.is_running else "⚪ Prêt (En attente)"
    conv_id = runner.active_conversation_id
    sess_str = f"Active (<code>{conv_id[:12]}…</code>)" if conv_id else ("Active" if runner.has_active_session else "Nouvelle session vierge")

    t_val = int(settings.get("timeout", 600))
    t_str = "♾️ Infini" if t_val <= 0 else (f"{t_val // 60} min" if t_val < 3600 else f"{t_val // 3600}h")

    _, sys_report, _ = await check_and_heal_services(auto_heal=False)

    st_msg = (
        f"🖥️ <b>Statut Global — {h(settings.get('agent_name', 'Antigravity Agent'))}</b>\n\n"
        f"• <b>État de l'Agent :</b> {running_str}\n"
        f"• <b>Antigravity CLI :</b> {agy_status}\n"
        f"• <b>Modèle IA :</b> <code>{h(settings.get('model', ''))}</code>\n"
        f"• <b>Effort / Mode :</b> <code>{h(settings.get('effort', 'auto'))}</code> / <code>{h(settings.get('mode', 'auto-approve'))}</code>\n"
        f"• <b>Multi-Agents :</b> {'🟢 Activé' if settings.get('multi_agent', True) else '🔴 Désactivé'}\n"
        f"• <b>Sandbox :</b> {'🔒 Activé' if settings.get('sandbox') else '🔓 Désactivé'}\n"
        f"• <b>Timeout :</b> <code>{t_str}</code>\n"
        f"• <b>Session :</b> {sess_str}\n"
        f"• <b>Tokens session :</b> <code>{runner.session_total_tokens:,}</code> ({runner.session_turns} tour(s))\n"
        f"• <b>Workspace :</b> <code>{h(settings.get('workspace_dir', ''))}</code>\n"
        f"• <b>RAM Bot :</b> <code>{mem_mb:.1f} Mo</code>\n\n"
        f"{sys_report}"
    )
    await update.message.reply_text(st_msg, parse_mode=PM)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    await update.message.reply_text(
        format_settings_summary_html(settings),
        reply_markup=get_settings_keyboard(settings),
        parse_mode=PM,
    )


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    models = await fetch_available_models(force_refresh=False)
    await update.message.reply_text(
        f"🧠 <b>Modèle Actif :</b> <code>{h(settings.get('model', ''))}</code>\n\n"
        "Sélectionnez un modèle Antigravity CLI ci-dessous :",
        reply_markup=get_model_selection_keyboard(settings.get("model", ""), models),
        parse_mode=PM,
    )


async def cmd_effort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    await update.message.reply_text(
        f"💡 <b>Niveau d'Effort Actif :</b> <code>{h(settings.get('effort', 'auto'))}</code>\n\n"
        "Choisissez la profondeur de réflexion d'Antigravity CLI :",
        reply_markup=get_effort_selection_keyboard(settings.get("effort", "auto")),
        parse_mode=PM,
    )


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    await update.message.reply_text(
        f"🛡️ <b>Mode d'Exécution Actif :</b> <code>{h(settings.get('mode', 'auto-approve'))}</code>\n\n"
        "Sélectionnez comment l'agent exécute ses outils et modifications :",
        reply_markup=get_mode_selection_keyboard(settings.get("mode", "auto-approve")),
        parse_mode=PM,
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    agents = await fetch_available_agents()
    multi_on = settings.get("multi_agent", True)
    prof = settings.get("agent_profile", "") or "Principal (Auto)"
    text = (
        "🤝 <b>Orchestration Multi-Agents & Sous-Agents</b>\n\n"
        f"• <b>Essaim Multi-Agents (Subagents) :</b> {'🟢 Activé' if multi_on else '🔴 Désactivé'}\n"
        f"• <b>Profil d'agent CLI (<code>--agent</code>) :</b> <code>{h(prof)}</code>\n\n"
        "<i>Lorsque le mode Multi-Agents est activé, l'agent principal peut créer et lancer "
        "des sous-agents spécialisés en parallèle (recherche, code, test) et afficher leur progression en direct !</i>"
    )
    await update.message.reply_text(text, reply_markup=get_agents_keyboard(settings, agents), parse_mode=PM)


async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    convs = load_conversations()
    active_id = runner.active_conversation_id
    lines = [
        "💬 <b>Gestionnaire de Sessions & Conversations CLI</b>\n",
        f"• <b>Session active :</b> <code>{active_id or 'Nouvelle session'}</code>",
        f"• <b>Tokens consommés (session) :</b> <code>{runner.session_total_tokens:,}</code> ({runner.session_turns} tours)\n",
    ]
    if convs:
        lines.append("<b>🕘 Conversations Récentes :</b>")
        for c in convs[:6]:
            mark = "🟢 " if c.get("id") == active_id else "• "
            lines.append(
                f"{mark}<code>{c.get('id', '')[:8]}</code> — <b>{h(c.get('title', 'Session'))}</b> "
                f"<i>({c.get('turns', 1)}t, {c.get('updated_at', '')})</i>"
            )
    else:
        lines.append("<i>Aucune conversation archivée pour le moment.</i>")

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_sessions_keyboard(convs, active_id),
        parse_mode=PM,
    )


async def cmd_mcp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    servers = await list_mcp_servers()
    lines = ["🔌 <b>Serveurs MCP (Model Context Protocol) — Antigravity CLI</b>\n"]
    if not servers:
        lines.append("<i>Aucun serveur MCP configuré dans Antigravity CLI.</i>")
    else:
        for s in servers:
            icon = "🟢" if s["status"] == "enabled" else "🔴"
            lines.append(
                f"• {icon} <b>{h(s['name'])}</b> [<code>{h(s['type'])}</code>] : <code>{h(s['target'][:60])}</code>"
            )
    lines.append("\n<i>Cliquez sur un serveur pour l'activer ou le désactiver instantanément :</i>")
    await update.message.reply_text("\n".join(lines), reply_markup=get_mcp_keyboard(servers), parse_mode=PM)


async def cmd_plugins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    raw_txt, plugins = await list_cli_plugins()
    lines = [
        "🧩 <b>Gestionnaire de Plugins — Antigravity CLI</b>\n",
        f"<pre>{h(raw_txt[:1000])}</pre>\n",
        "<i>Gérez, installez ou importez vos plugins en un clic :</i>",
    ]
    await update.message.reply_text("\n".join(lines), reply_markup=get_plugins_keyboard(plugins), parse_mode=PM)


async def cmd_remote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    _, status_txt = await manage_remote_control("status")
    rc_flag = bool(settings.get("remote_control", False))
    text = (
        "🌐 <b>Antigravity Remote Control</b>\n\n"
        f"• <b>Flag de session (<code>--remote-control</code>) :</b> {'🟢 Activé' if rc_flag else '⚪ Désactivé'}\n"
        f"• <b>Statut du Démon :</b>\n<pre>{h(status_txt)}</pre>\n\n"
        "<i>Remote Control vous permet de piloter vos sessions CLI depuis votre navigateur sur antigravity.google.</i>"
    )
    await update.message.reply_text(text, reply_markup=get_remote_control_keyboard(rc_flag), parse_mode=PM)


async def cmd_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    ws = settings.get("workspace_dir", str(config.WORKSPACE_DIR))
    extra = settings.get("extra_dirs", []) or []
    lines = [
        "📁 <b>Configuration du Workspace & Répertoires</b>\n",
        f"• <b>Workspace Principal (<code>cwd</code>) :</b>\n  <code>{h(ws)}</code>\n",
    ]
    if extra:
        lines.append("• <b>Répertoires Secondaires (<code>--add-dir</code>) :</b>")
        for d in extra:
            lines.append(f"  ◦ <code>{h(d)}</code>")
    else:
        lines.append("• <b>Répertoires Secondaires (<code>--add-dir</code>) :</b> <i>Aucun</i>")

    await update.message.reply_text("\n".join(lines), reply_markup=get_workspace_keyboard(settings), parse_mode=PM)


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    msg = await update.message.reply_text(
        "🔍 <i>Vérification des mises à jour sur GitHub et de la version d'Antigravity CLI...</i>",
        parse_mode=PM,
    )
    info = await check_for_updates()
    await safe_edit_message(
        msg,
        format_update_check_html(info, is_push_alert=False),
        reply_markup=get_update_prompt_keyboard(info),
    )


async def cmd_update_cli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    msg = await update.message.reply_text("⬆️ <i>Vérification et mise à jour d'Antigravity CLI (<code>agy update</code>) en cours...</i>", parse_mode=PM)
    ok, out = await update_cli_binary()
    await safe_edit_message(
        msg,
        f"{'✅' if ok else 'ℹ️'} <b>Mise à jour Antigravity CLI :</b>\n<pre>{h(out[:1500])}</pre>",
    )


async def dispatch_custom_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    cmd_name: str,
    user_args: str,
):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return

    cmd_data = command_mgr.get_command(cmd_name)
    if not cmd_data:
        await update.message.reply_text(f"❌ Commande <code>/{h(cmd_name)}</code> non reconnue.", parse_mode=PM)
        return

    enhanced_prompt, overrides = command_mgr.format_command_prompt(cmd_name, user_args)
    effective_settings = {**settings, **overrides}

    header = (
        f"🕹️ <b>Commande :</b> <code>/{h(cmd_name)}</code>\n"
        f"<i>{h(cmd_data.get('description', ''))}</i>\n\n"
    )
    await _process_user_turn(
        update, context, enhanced_prompt, header=header, custom_settings=effective_settings
    )


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    args = context.args or []

    if not args:
        customs = command_mgr.list_commands()
        lines = [
            "📋 <b>Gestionnaire de Commandes Dynamiques</b>\n",
            "Ces commandes sont synchronisées avec Telegram et apparaissent dans le menu <code>/</code>.\n",
            "<b>🕹️ Commandes Actives :</b>",
        ]
        if not customs:
            lines.append("<i>Aucune commande personnalisée active.</i>")
        else:
            for k, v in customs.items():
                lines.append(f"• <code>/{h(k)}</code> : {h(v.get('description', ''))}")
                if v.get("overrides"):
                    lines.append(f"  └ <i>Overrides : <code>{h(str(v['overrides']))}</code></i>")

        lines.append("\n<b>💡 Syntaxe rapide :</b>")
        lines.append("• Ajouter : <code>/commands add &lt;nom&gt; &lt;description&gt; | &lt;template avec {prompt}&gt;</code>")
        lines.append("• Supprimer : <code>/commands remove &lt;nom&gt;</code>")
        await update.message.reply_text("\n".join(lines), parse_mode=PM)
        return

    subcmd = args[0].lower()
    if subcmd == "add":
        rest = " ".join(args[1:]).strip()
        if "|" in rest:
            meta_part, tpl = rest.split("|", 1)
            tokens = meta_part.strip().split(maxsplit=1)
            if len(tokens) < 2:
                await update.message.reply_text(
                    "Usage : <code>/commands add &lt;nom&gt; &lt;description&gt; | &lt;template {prompt}&gt;</code>",
                    parse_mode=PM,
                )
                return
            name, desc = tokens[0], tokens[1].strip()
        else:
            tokens = rest.split(maxsplit=2)
            if len(tokens) < 3:
                await update.message.reply_text(
                    "Usage : <code>/commands add &lt;nom&gt; &lt;description&gt; &lt;template {prompt}&gt;</code>",
                    parse_mode=PM,
                )
                return
            name, desc, tpl = tokens[0], tokens[1], tokens[2]

        ok, msg = command_mgr.add_command(name, desc, tpl, created_by="user")
        if ok:
            await sync_telegram_commands(context.bot)
            await update.message.reply_text(f"✅ {h(msg)}\nLe menu Telegram a été mis à jour !", parse_mode=PM)
        else:
            await update.message.reply_text(f"❌ {h(msg)}", parse_mode=PM)

    elif subcmd in ("remove", "rm", "delete"):
        if len(args) < 2:
            await update.message.reply_text("Usage : <code>/commands remove &lt;nom&gt;</code>", parse_mode=PM)
            return
        ok, msg = command_mgr.remove_command(args[1])
        if ok:
            await sync_telegram_commands(context.bot)
            await update.message.reply_text(f"✅ {h(msg)}", parse_mode=PM)
        else:
            await update.message.reply_text(f"❌ {h(msg)}", parse_mode=PM)
    else:
        await update.message.reply_text(
            "Sous-commandes : <code>/commands</code>, <code>/commands add</code>, <code>/commands remove</code>",
            parse_mode=PM,
        )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return

    users = auth_mgr.list_all_users()
    total = len(users)
    admins = sum(1 for u in users.values() if u.get("role") == ROLE_ADMIN)
    blocked = sum(1 for u in users.values() if u.get("role") == ROLE_BLOCKED)
    pending = sum(1 for u in users.values() if u.get("role") == ROLE_PENDING)

    text = (
        "👥 <b>Gestion des Utilisateurs & Accès</b>\n\n"
        f"• <b>Total inscrits :</b> <code>{total}</code>\n"
        f"• 👑 <b>Administrateurs :</b> <code>{admins}</code>\n"
        f"• ⏳ <b>En attente :</b> <code>{pending}</code>\n"
        f"• 🚫 <b>Bloqués :</b> <code>{blocked}</code>\n\n"
        "<i>Cliquez sur un utilisateur ci-dessous pour modifier ses permissions :</i>"
    )
    await update.message.reply_text(text, reply_markup=_get_users_dashboard_keyboard(), parse_mode=PM)


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    args = context.args
    if args:
        q = " ".join(args)
        results = search_memories(q, limit=5)
        if not results:
            await update.message.reply_text(f"🔍 Aucun souvenir correspondant à : <code>{h(q)}</code>", parse_mode=PM)
            return
        lines = [f"🔍 <b>Résultats sémantiques pour :</b> <code>{h(q)}</code>\n"]
        for r in results:
            lines.append(f"🔹 <b>#{r['id']}</b> [{h(r['category'])}] (score: {r['score']}) :\n<i>{h(r['content'])}</i>\n")
        await update.message.reply_text("\n".join(lines), parse_mode=PM)
    else:
        await update.message.reply_text(get_summary_html(), parse_mode=PM)


async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    if not context.args:
        await update.message.reply_text("Usage : <code>/remember &lt;information à mémoriser&gt;</code>", parse_mode=PM)
        return
    text = " ".join(context.args)
    mid = add_or_update_memory(content=text, category="user_note", importance=4)
    await update.message.reply_text(
        f"🧠 <b>Souvenir mémorisé avec succès !</b> (ID: <code>#{mid}</code>)\n<i>{h(text)}</i>",
        parse_mode=PM,
    )


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.message.reply_text("Usage : <code>/forget &lt;ID_souvenir&gt;</code>", parse_mode=PM)
        return
    mid = int(context.args[0].lstrip("#"))
    if delete_memory(mid):
        await update.message.reply_text(f"🗑️ Souvenir <code>#{mid}</code> supprimé.", parse_mode=PM)
    else:
        await update.message.reply_text(f"❌ Souvenir <code>#{mid}</code> introuvable.", parse_mode=PM)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    runner.reset_session()
    pending_admin_input.pop(update.effective_user.id, None)
    await update.message.reply_text("🧹 <b>Session réinitialisée !</b> Une nouvelle conversation vierge est prête.", parse_mode=PM)


async def cmd_abort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    if runner.is_running:
        success = await runner.abort()
        if success:
            await update.message.reply_text("🛑 <b>Tâche interrompue immédiatement.</b>", parse_mode=PM)
        else:
            await update.message.reply_text("⚠️ Impossible d'arrêter le processus.", parse_mode=PM)
    else:
        await update.message.reply_text("ℹ️ Aucune tâche n'est en cours d'exécution.", parse_mode=PM)


def _get_services_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Actualiser", callback_data="srv:refresh"),
            InlineKeyboardButton("🩹 Auto-Heal Services", callback_data="srv:heal"),
        ],
        [
            InlineKeyboardButton("🛡️ Auto-Heal Logs", callback_data="autoheal:menu"),
            InlineKeyboardButton("❌ Fermer", callback_data="close_menu"),
        ],
    ])


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    status_msg = await update.message.reply_text("🔍 <i>Inspection du système...</i>", parse_mode=PM)
    _, report_html, _ = await check_and_heal_services(auto_heal=False)
    await safe_edit_message(status_msg, report_html, reply_markup=_get_services_keyboard())


async def cmd_autoheal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    await update.message.reply_text(
        log_scanner.get_dashboard_text(),
        reply_markup=log_scanner.get_dashboard_keyboard(),
        parse_mode=PM,
    )


# =============================================================================
# Callback Query Handler (Interactive Menus & Control Center)
# =============================================================================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data or ""

    if data == "noop":
        await query.answer()
        return

    if data == "guest_req:ask":
        await query.answer()
        name = query.from_user.first_name or "Utilisateur"
        username = query.from_user.username or ""
        auth_mgr.register_access_request(uid, name, username)
        await safe_edit_message(
            query.message,
            "📨 <b>Votre demande d'accès a été transmise à l'administrateur !</b>\n\n"
            "Vous recevrez une notification dès qu'elle aura été validée.",
        )
        admin_id = auth_mgr.get_primary_admin_id()
        if admin_id:
            try:
                admin_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("👑 Accepter (Admin)", callback_data=f"auth:role:{uid}:{ROLE_ADMIN}"),
                        InlineKeyboardButton("🚫 Refuser", callback_data=f"auth:role:{uid}:{ROLE_BLOCKED}"),
                    ]
                ])
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "👤 <b>Nouvelle demande d'accès au Bot !</b>\n\n"
                        f"• <b>Nom :</b> {h(name)}\n"
                        f"• <b>Username :</b> @{h(username) if username else 'aucun'}\n"
                        f"• <b>ID Telegram :</b> <code>{uid}</code>\n\n"
                        "Voulez-vous autoriser cet utilisateur ?"
                    ),
                    reply_markup=admin_kb,
                    parse_mode=PM,
                )
            except Exception as ex:
                logger.warning(f"Could not notify admin of access request: {ex}")
        return

    if not is_admin(uid, query.from_user):
        await query.answer("⛔ Réservé à l'administrateur.", show_alert=True)
        return

    if data == "abort_running":
        if runner.is_running:
            await runner.abort()
            await query.answer("🛑 Exécution interrompue !", show_alert=False)
        else:
            await query.answer("ℹ️ Déjà terminé.", show_alert=False)
        return

    if data == "close_menu":
        await query.answer()
        try:
            await query.delete_message()
        except Exception:
            pass
        return

    # --- User Management (RBAC) ---
    if data.startswith("auth:"):
        await query.answer()
        if data == "auth:refresh":
            users = auth_mgr.list_all_users()
            total = len(users)
            admins = sum(1 for u in users.values() if u.get("role") == ROLE_ADMIN)
            blocked = sum(1 for u in users.values() if u.get("role") == ROLE_BLOCKED)
            pending = sum(1 for u in users.values() if u.get("role") == ROLE_PENDING)
            text = (
                "👥 <b>Gestion des Utilisateurs</b>\n\n"
                f"• <b>Total inscrits :</b> <code>{total}</code>\n"
                f"• 👑 <b>Admins :</b> <code>{admins}</code> | ⏳ <b>En attente :</b> <code>{pending}</code> | 🚫 <b>Bloqués :</b> <code>{blocked}</code>"
            )
            await safe_edit_message(query.message, text, reply_markup=_get_users_dashboard_keyboard())
        elif data.startswith("auth:view:"):
            target_uid = data.split(":")[2]
            u = auth_mgr.get_user(int(target_uid)) or {}
            name = u.get("name") or "Inconnu"
            username = u.get("username")
            role = u.get("role", ROLE_BLOCKED)
            text = (
                f"👤 <b>Fiche Utilisateur : {h(name)}</b>\n\n"
                f"• <b>ID Telegram :</b> <code>{target_uid}</code>\n"
                f"• <b>Username :</b> @{h(username) if username else 'aucun'}\n"
                f"• <b>Rôle :</b> <code>{role}</code> ({ROLES_DESCRIPTION.get(role, '')})"
            )
            await safe_edit_message(query.message, text, reply_markup=_get_user_detail_keyboard(target_uid))
        elif data.startswith("auth:role:"):
            parts = data.split(":")
            target_uid, new_role = parts[2], parts[3]
            auth_mgr.set_user_role(int(target_uid), new_role)
            try:
                if new_role == ROLE_ADMIN:
                    await context.bot.send_message(
                        chat_id=int(target_uid),
                        text="🎉 <b>Votre accès Administrateur au bot Antigravity a été activé !</b>",
                        parse_mode=PM,
                    )
                elif new_role == ROLE_BLOCKED:
                    await context.bot.send_message(
                        chat_id=int(target_uid),
                        text="⛔ Votre accès au bot a été révoqué.",
                        parse_mode=PM,
                    )
            except Exception:
                pass
            u = auth_mgr.get_user(int(target_uid)) or {}
            text = (
                f"👤 <b>Fiche Utilisateur : {h(u.get('name', 'Inconnu'))}</b>\n\n"
                f"• <b>ID Telegram :</b> <code>{target_uid}</code>\n"
                f"• <b>Rôle :</b> <code>{new_role}</code> ✅"
            )
            await safe_edit_message(query.message, text, reply_markup=_get_user_detail_keyboard(target_uid))
        elif data.startswith("auth:delete:"):
            target_uid = data.split(":")[2]
            auth_mgr.delete_user(int(target_uid))
            await safe_edit_message(
                query.message,
                f"🗑️ Utilisateur <code>{target_uid}</code> supprimé.",
                reply_markup=_get_users_dashboard_keyboard(),
            )
        return

    # --- Control Center Navigation & Settings ---
    if data == "menu_main":
        await query.answer()
        pending_admin_input.pop(uid, None)
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data == "menu_mode":
        await query.answer()
        await safe_edit_message(
            query.message,
            "🛡️ <b>Mode d'Exécution Antigravity CLI :</b>\n\n"
            "• <b>⚡ Autonome :</b> Exécute toutes les actions et commandes sans bloquer (<code>--dangerously-skip-permissions</code>).\n"
            "• <b>✏️ Accepter Éditions :</b> Autorise l'édition de fichiers (<code>--mode accept-edits</code>).\n"
            "• <b>📋 Planification :</b> Analyse et conçoit un plan sans modifier le système (<code>--mode plan</code>).",
            reply_markup=get_mode_selection_keyboard(settings.get("mode", "auto-approve")),
        )
        return

    if data == "menu_model":
        await query.answer()
        models = await fetch_available_models(force_refresh=False)
        await safe_edit_message(
            query.message,
            f"🧠 <b>Sélectionnez le Modèle d'IA Principal :</b>\n"
            f"Modèle actuel : <code>{h(settings.get('model', ''))}</code>",
            reply_markup=get_model_selection_keyboard(settings.get("model", ""), models),
        )
        return

    if data == "refresh_models":
        await query.answer("🔄 Interrogation de `agy models` en cours...")
        models = await fetch_available_models(force_refresh=True)
        await safe_edit_message(
            query.message,
            f"✅ <b>Liste des modèles synchronisée avec Antigravity CLI ({len(models)} modèles) !</b>\n"
            f"Modèle actuel : <code>{h(settings.get('model', ''))}</code>",
            reply_markup=get_model_selection_keyboard(settings.get("model", ""), models),
        )
        return

    if data == "menu_effort":
        await query.answer()
        await safe_edit_message(
            query.message,
            "💡 <b>Niveau d'Effort de Réflexion (<code>--effort</code>) :</b>\n\n"
            "Contrôle le budget de réflexion interne du modèle avant de répondre.",
            reply_markup=get_effort_selection_keyboard(settings.get("effort", "auto")),
        )
        return

    if data == "menu_timeout":
        await query.answer()
        await safe_edit_message(
            query.message,
            "⏱️ <b>Délai d'Exécution Maximal (Timeout) :</b>",
            reply_markup=get_timeout_selection_keyboard(int(settings.get("timeout", 600))),
        )
        return

    if data == "menu_verbosity":
        await query.answer()
        await safe_edit_message(
            query.message,
            "👁️ <b>Niveau de Détail de l'Affichage :</b>",
            reply_markup=get_verbosity_selection_keyboard(settings.get("verbosity", "normal")),
        )
        return

    if data == "toggle_sandbox":
        settings["sandbox"] = not bool(settings.get("sandbox", False))
        save_settings(settings)
        state_str = "activé 🔒" if settings["sandbox"] else "désactivé 🔓"
        await query.answer(f"Mode Sandbox {state_str}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data == "toggle_autofiles":
        settings["auto_send_files"] = not bool(settings.get("auto_send_files", True))
        save_settings(settings)
        state_str = "activé ✅" if settings["auto_send_files"] else "désactivé ❌"
        await query.answer(f"Envoi automatique des fichiers {state_str}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data == "menu_agents":
        await query.answer()
        agents = await fetch_available_agents()
        multi_on = settings.get("multi_agent", True)
        prof = settings.get("agent_profile", "") or "Principal (Auto)"
        text = (
            "🤝 <b>Orchestration Multi-Agents & Sous-Agents</b>\n\n"
            f"• <b>Essaim Multi-Agents :</b> {'🟢 Activé' if multi_on else '🔴 Désactivé'}\n"
            f"• <b>Profil d'agent CLI (<code>--agent</code>) :</b> <code>{h(prof)}</code>"
        )
        await safe_edit_message(query.message, text, reply_markup=get_agents_keyboard(settings, agents))
        return

    if data == "toggle_multi_agent":
        settings["multi_agent"] = not bool(settings.get("multi_agent", True))
        save_settings(settings)
        await query.answer(f"Multi-Agents {'activé ✅' if settings['multi_agent'] else 'désactivé ❌'}")
        agents = await fetch_available_agents()
        await safe_edit_message(
            query.message,
            "🤝 <b>Orchestration Multi-Agents mise à jour !</b>",
            reply_markup=get_agents_keyboard(settings, agents),
        )
        return

    if data.startswith("set_agent:"):
        ag_name = data.split(":", 1)[1]
        settings["agent_profile"] = ag_name
        save_settings(settings)
        await query.answer(f"Profil d'agent défini : {ag_name or 'Auto'}")
        agents = await fetch_available_agents()
        await safe_edit_message(
            query.message,
            f"✅ <b>Profil d'agent CLI défini sur :</b> <code>{h(ag_name or 'Principal (Auto)')}</code>",
            reply_markup=get_agents_keyboard(settings, agents),
        )
        return

    if data.startswith("set_mode:"):
        settings["mode"] = data.split(":", 1)[1]
        save_settings(settings)
        await query.answer(f"Mode : {settings['mode']}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data.startswith("set_model:"):
        settings["model"] = data.split(":", 1)[1]
        save_settings(settings)
        await query.answer(f"Modèle : {settings['model']}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data.startswith("set_effort:"):
        settings["effort"] = data.split(":", 1)[1]
        save_settings(settings)
        await query.answer(f"Effort : {settings['effort']}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data.startswith("set_timeout:"):
        settings["timeout"] = int(data.split(":", 1)[1])
        save_settings(settings)
        await query.answer("Timeout mis à jour")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data.startswith("set_verbosity:"):
        settings["verbosity"] = data.split(":", 1)[1]
        save_settings(settings)
        await query.answer(f"Affichage : {settings['verbosity']}")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    if data == "reset_settings":
        settings.clear()
        settings.update(DEFAULT_SETTINGS)
        save_settings(settings)
        await query.answer("Paramètres réinitialisés !")
        await safe_edit_message(
            query.message,
            format_settings_summary_html(settings),
            reply_markup=get_settings_keyboard(settings),
        )
        return

    # --- MCP Servers Menu ---
    if data == "menu_mcp":
        await query.answer("Chargement des serveurs MCP...")
        servers = await list_mcp_servers()
        lines = ["🔌 <b>Serveurs MCP (Antigravity CLI)</b>\n"]
        if not servers:
            lines.append("<i>Aucun serveur MCP configuré.</i>")
        else:
            for s in servers:
                icon = "🟢" if s["status"] == "enabled" else "🔴"
                lines.append(f"• {icon} <b>{h(s['name'])}</b> [<code>{h(s['type'])}</code>] : <code>{h(s['target'][:50])}</code>")
        lines.append("\n<i>Cliquez sur un serveur pour basculer son état (Actif / Inactif) :</i>")
        await safe_edit_message(query.message, "\n".join(lines), reply_markup=get_mcp_keyboard(servers))
        return

    if data.startswith("mcp_toggle:"):
        parts = data.split(":", 2)
        act, srv_name = parts[1], parts[2]
        enable = (act == "enable")
        await query.answer(f"{'Activation' if enable else 'Désactivation'} de {srv_name}...")
        ok, msg = await toggle_mcp_server(srv_name, enable)
        servers = await list_mcp_servers()
        await safe_edit_message(
            query.message,
            f"{'✅' if ok else '⚠️'} <code>{h(msg)}</code>\n\n🔌 <b>Serveurs MCP :</b>",
            reply_markup=get_mcp_keyboard(servers),
        )
        return

    if data == "mcp_catalog":
        await query.answer("Chargement du catalogue MCP...")
        servers = await list_mcp_servers()
        installed_names = [s["name"] for s in servers]
        lines = [
            "⚡ <b>Catalogue des Serveurs MCP Recommandés (Installation en 1 Clic)</b>\n",
            "Cliquez sur un serveur ci-dessous pour l'installer et l'activer automatiquement dans Antigravity CLI :\n",
        ]
        for srv in config.RECOMMENDED_MCP_SERVERS:
            st = "✅ Installé" if srv["id"] in installed_names else "⚪ Disponible"
            lines.append(f"• <b>{h(srv['title'])}</b> [{st}]\n  <i>{h(srv['description'])}</i>")
        await safe_edit_message(
            query.message,
            "\n".join(lines),
            reply_markup=get_mcp_catalog_keyboard(installed_names),
        )
        return

    if data.startswith("mcp_quick_install:"):
        target_id = data.split(":", 1)[1]
        await query.answer("Installation MCP en cours...")
        if target_id == "all_default":
            results = []
            for srv in config.RECOMMENDED_MCP_SERVERS:
                if srv.get("default_selected"):
                    ok, msg = await install_recommended_mcp_server(srv["id"])
                    results.append(f"{'✅' if ok else '⚠️'} <b>{h(srv['id'])}</b> : <code>{h(msg)}</code>")
            summary = "\n".join(results)
        else:
            ok, msg = await install_recommended_mcp_server(target_id)
            summary = f"{'✅' if ok else '⚠️'} <b>{h(target_id)}</b> : <code>{h(msg)}</code>"

        servers = await list_mcp_servers()
        installed_names = [s["name"] for s in servers]
        await safe_edit_message(
            query.message,
            f"🔌 <b>Résultat de l'installation MCP :</b>\n{summary}\n\n"
            "<i>Cliquez sur un autre serveur ou revenez à la liste active :</i>",
            reply_markup=get_mcp_catalog_keyboard(installed_names),
        )
        return

    if data == "mcp_add_prompt":
        await query.answer()
        pending_admin_input[uid] = "mcp_add"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_mcp")]])
        await safe_edit_message(
            query.message,
            "➕ <b>Ajouter un Serveur MCP à Antigravity CLI</b>\n\n"
            "Envoyez maintenant la commande d'ajout au format :\n"
            "<code>&lt;nom&gt; &lt;commande_ou_url&gt;</code>\n\n"
            "<i>Exemple : <code>playwright npx -y @playwright/mcp@latest</code></i>",
            reply_markup=kb,
        )
        return

    # --- Plugins Menu ---
    if data == "menu_plugins":
        await query.answer("Chargement des plugins...")
        raw_txt, plugins = await list_cli_plugins()
        lines = [
            "🧩 <b>Plugins Antigravity CLI</b>\n",
            f"<pre>{h(raw_txt[:1000])}</pre>",
        ]
        await safe_edit_message(query.message, "\n".join(lines), reply_markup=get_plugins_keyboard(plugins))
        return

    if data.startswith("plugin_toggle:"):
        parts = data.split(":", 2)
        act, pl_name = parts[1], parts[2]
        await query.answer(f"Plugin {pl_name} : {act}...")
        ok, msg = await run_plugin_action(act, pl_name)
        raw_txt, plugins = await list_cli_plugins()
        await safe_edit_message(
            query.message,
            f"{'✅' if ok else '⚠️'} <code>{h(msg)}</code>\n\n<pre>{h(raw_txt[:1000])}</pre>",
            reply_markup=get_plugins_keyboard(plugins),
        )
        return

    if data.startswith("plugin_import:"):
        src = data.split(":", 1)[1]
        await query.answer(f"Importation depuis {src}...")
        ok, msg = await run_plugin_action("import", src)
        raw_txt, plugins = await list_cli_plugins()
        await safe_edit_message(
            query.message,
            f"{'✅' if ok else 'ℹ️'} <b>Import {h(src)} :</b> <code>{h(msg)}</code>\n\n<pre>{h(raw_txt[:1000])}</pre>",
            reply_markup=get_plugins_keyboard(plugins),
        )
        return

    if data == "plugin_install_prompt":
        await query.answer()
        pending_admin_input[uid] = "plugin_install"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_plugins")]])
        await safe_edit_message(
            query.message,
            "➕ <b>Installer un Plugin Antigravity CLI</b>\n\n"
            "Envoyez le nom ou chemin du plugin à installer (ex: <code>nom_plugin</code>) :",
            reply_markup=kb,
        )
        return

    # --- Remote Control Menu ---
    if data == "menu_remote":
        await query.answer("Vérification de Remote Control...")
        _, status_txt = await manage_remote_control("status")
        rc_flag = bool(settings.get("remote_control", False))
        text = (
            "🌐 <b>Antigravity Remote Control</b>\n\n"
            f"• <b>Flag de session (<code>--remote-control</code>) :</b> {'🟢 Activé' if rc_flag else '⚪ Désactivé'}\n"
            f"• <b>Statut du Démon :</b>\n<pre>{h(status_txt)}</pre>"
        )
        await safe_edit_message(query.message, text, reply_markup=get_remote_control_keyboard(rc_flag))
        return

    if data.startswith("rc_action:"):
        act = data.split(":", 1)[1]
        if act == "toggle_flag":
            settings["remote_control"] = not bool(settings.get("remote_control", False))
            save_settings(settings)
            await query.answer(f"Flag --remote-control : {'ON' if settings['remote_control'] else 'OFF'}")
            _, status_txt = await manage_remote_control("status")
        else:
            await query.answer(f"Exécution : remote-control {act}...")
            _, status_txt = await manage_remote_control(act)
        rc_flag = bool(settings.get("remote_control", False))
        text = (
            "🌐 <b>Antigravity Remote Control</b>\n\n"
            f"• <b>Flag de session (<code>--remote-control</code>) :</b> {'🟢 Activé' if rc_flag else '⚪ Désactivé'}\n"
            f"• <b>Résultat / Statut :</b>\n<pre>{h(status_txt)}</pre>"
        )
        await safe_edit_message(query.message, text, reply_markup=get_remote_control_keyboard(rc_flag))
        return

    # --- Sessions & History Menu ---
    if data == "menu_sessions":
        await query.answer()
        convs = load_conversations()
        active_id = runner.active_conversation_id
        text = (
            "💬 <b>Sessions & Historique des Conversations</b>\n\n"
            f"• <b>Conversation active :</b> <code>{active_id or 'Nouvelle session'}</code>\n"
            f"• <b>Tokens session :</b> <code>{runner.session_total_tokens:,}</code> ({runner.session_turns} tour(s))\n\n"
            "<i>Sélectionnez une conversation pour la reprendre, ou démarrez une session vierge :</i>"
        )
        await safe_edit_message(query.message, text, reply_markup=get_sessions_keyboard(convs, active_id))
        return

    if data == "sess_new":
        runner.reset_session()
        await query.answer("🧹 Nouvelle session démarrée !")
        convs = load_conversations()
        await safe_edit_message(
            query.message,
            "🧹 <b>Session réinitialisée !</b> La prochaine demande créera une nouvelle conversation.",
            reply_markup=get_sessions_keyboard(convs, None),
        )
        return

    if data.startswith("sess_load:"):
        cid = data.split(":", 1)[1]
        runner.set_conversation(cid)
        await query.answer(f"Session reprise : {cid[:8]}")
        convs = load_conversations()
        await safe_edit_message(
            query.message,
            f"✅ <b>Conversation reprise :</b> <code>{h(cid)}</code>\n"
            "Vos prochains messages continueront directement cette session.",
            reply_markup=get_sessions_keyboard(convs, cid),
        )
        return

    # --- Workspace Menu ---
    if data == "menu_workspace":
        await query.answer()
        ws = settings.get("workspace_dir", str(config.WORKSPACE_DIR))
        extra = settings.get("extra_dirs", []) or []
        lines = [
            "📁 <b>Dossier de Travail (Workspace) & Dossiers Secondaires</b>\n",
            f"• <b>Workspace Principal :</b> <code>{h(ws)}</code>",
            f"• <b>Dossiers <code>--add-dir</code> :</b> {len(extra)}",
        ]
        for d in extra:
            lines.append(f"  ◦ <code>{h(d)}</code>")
        await safe_edit_message(query.message, "\n".join(lines), reply_markup=get_workspace_keyboard(settings))
        return

    if data == "ws_change_prompt":
        await query.answer()
        pending_admin_input[uid] = "ws_change"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_workspace")]])
        await safe_edit_message(
            query.message,
            "📂 <b>Changer le Dossier Workspace Principal</b>\n\n"
            f"Actuel : <code>{h(settings.get('workspace_dir', ''))}</code>\n\n"
            "Envoyez maintenant le chemin absolu du nouveau dossier :",
            reply_markup=kb,
        )
        return

    if data == "ws_add_extra_prompt":
        await query.answer()
        pending_admin_input[uid] = "ws_add_extra"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_workspace")]])
        await safe_edit_message(
            query.message,
            "➕ <b>Ajouter un Dossier Secondaire (<code>--add-dir</code>)</b>\n\n"
            "Envoyez le chemin absolu du dossier supplémentaire à inclure dans le contexte de l'agent :",
            reply_markup=kb,
        )
        return

    if data == "ws_clear_extra":
        settings["extra_dirs"] = []
        save_settings(settings)
        await query.answer("Dossiers secondaires vidés !")
        await safe_edit_message(
            query.message,
            "✅ <b>Liste des dossiers secondaires vidée.</b>",
            reply_markup=get_workspace_keyboard(settings),
        )
        return

    # --- Persona & Custom Instructions Menu ---
    if data == "menu_persona":
        await query.answer()
        ag_name = settings.get("agent_name", "Antigravity Agent")
        instr = settings.get("custom_instructions", "").strip() or "(Aucune instruction personnalisée)"
        text = (
            "✏️ <b>Identité & Instructions Personnalisées de l'Agent</b>\n\n"
            f"• <b>Nom de l'Agent :</b> <code>{h(ag_name)}</code>\n"
            f"• <b>Instructions Système Additionnelles :</b>\n<blockquote>{h(instr[:600])}</blockquote>"
        )
        await safe_edit_message(query.message, text, reply_markup=get_persona_keyboard(settings))
        return

    if data == "persona_name_prompt":
        await query.answer()
        pending_admin_input[uid] = "persona_name"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_persona")]])
        await safe_edit_message(
            query.message,
            "🏷️ <b>Changer le Nom de l'Agent</b>\n\nEnvoyez le nouveau nom souhaité pour votre agent IA :",
            reply_markup=kb,
        )
        return

    if data == "persona_instr_prompt":
        await query.answer()
        pending_admin_input[uid] = "persona_instr"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_persona")]])
        await safe_edit_message(
            query.message,
            "📝 <b>Définir des Instructions Système Personnalisées</b>\n\n"
            "Envoyez les consignes permanentes que l'agent devra toujours respecter :",
            reply_markup=kb,
        )
        return

    if data == "persona_clear_instr":
        settings["custom_instructions"] = ""
        save_settings(settings)
        await query.answer("Instructions personnalisées effacées !")
        await safe_edit_message(
            query.message,
            "✅ <b>Instructions personnalisées effacées.</b>",
            reply_markup=get_persona_keyboard(settings),
        )
        return

    # --- System & CLI Auto-Update ---
    if data == "sys_update:check":
        await query.answer("Vérification sur GitHub...")
        await safe_edit_message(
            query.message,
            "🔍 <i>Vérification des mises à jour sur GitHub et de la compatibilité Antigravity CLI...</i>",
        )
        info = await check_for_updates()
        await safe_edit_message(
            query.message,
            format_update_check_html(info, is_push_alert=False),
            reply_markup=get_update_prompt_keyboard(info),
        )
        return

    if data == "sys_update:files":
        await query.answer("Chargement des fichiers modifiés...")
        info = await check_for_updates()
        files = info.get("changed_files", []) or []
        files_txt = "\n".join(f"• <code>{h(f)}</code>" for f in files[:25]) or "<i>Aucun fichier modifié.</i>"
        if len(files) > 25:
            files_txt += f"\n<i>... et {len(files) - 25} autres fichiers.</i>"
        await safe_edit_message(
            query.message,
            f"📂 <b>Fichiers modifiés dans cette mise à jour ({len(files)}) :</b>\n\n{files_txt}\n\n"
            "🛡️ <i>Vos données personnelles (<code>.env</code>, <code>memory.db</code>, discussions, skills) ne seront pas touchées.</i>",
            reply_markup=get_update_prompt_keyboard(info),
        )
        return

    if data.startswith("sys_update:dismiss:"):
        sha_part = data.split(":", 2)[2]
        info = await check_for_updates()
        full_sha = info.get("remote_sha_full") or sha_part
        mark_commit_dismissed(full_sha)
        await query.answer("Mise à jour reportée.")
        await safe_edit_message(
            query.message,
            "⏳ <b>Mise à jour reportée.</b>\n"
            "<i>Vous pourrez la lancer à tout moment via <code>/update</code> ou depuis <code>/settings</code>.</i>",
        )
        return

    if data == "sys_update:confirm":
        if runner.is_running:
            await query.answer("⚠️ Une tâche IA est en cours. Attendez sa fin ou tapez /abort.", show_alert=True)
            return
        await query.answer("🚀 Lancement de la mise à jour automatique...")

        async def _progress(step_text: str):
            await safe_edit_message(
                query.message,
                f"🚀 <b>Mise à Jour Automatique en Cours...</b>\n\n{h(step_text)}",
            )

        ok, res_msg = await perform_safe_update(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            on_progress=_progress,
        )
        if not ok:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour", callback_data="sys_update:check")]])
            await safe_edit_message(
                query.message,
                f"❌ <b>Échec de la mise à jour automatique :</b>\n<code>{h(res_msg)}</code>\n\n"
                "🛡️ <i>Vos données et votre configuration actuelle sont restées intactes.</i>",
                reply_markup=kb,
            )
            return

        # Trigger detached restarter and exit current process cleanly
        spawn_detached_restarter(os.getpid())
        await asyncio.sleep(0.8)
        os._exit(0)

    if data == "cli_update":
        await query.answer("Mise à jour d'Antigravity CLI en cours...")
        await safe_edit_message(
            query.message,
            "⬆️ <i>Exécution de <code>agy update</code> en cours...</i>",
        )
        ok, out = await update_cli_binary()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")]])
        await safe_edit_message(
            query.message,
            f"{'✅' if ok else 'ℹ️'} <b>Résultat <code>agy update</code> :</b>\n<pre>{h(out[:1500])}</pre>",
            reply_markup=kb,
        )
        return

    # --- Dynamic Commands Menu ---
    if data == "menu_commands":
        await query.answer()
        customs = command_mgr.list_commands()
        lines = [
            "🕹️ <b>Commandes Personnalisées Actives</b>\n",
        ]
        for k, v in customs.items():
            lines.append(f"• <code>/{h(k)}</code> : {h(v.get('description', ''))}")
        lines.append("\n💡 <i>Utilisez <code>/commands add &lt;nom&gt; &lt;desc&gt; | &lt;template&gt;</code> pour en ajouter.</i>")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")],
            [InlineKeyboardButton("❌ Fermer", callback_data="close_menu")],
        ])
        await safe_edit_message(query.message, "\n".join(lines), reply_markup=kb)
        return

    # --- Services & Auto-Heal ---
    if data.startswith("srv:"):
        await query.answer()
        if data == "srv:refresh":
            _, report_html, _ = await check_and_heal_services(auto_heal=False)
            await safe_edit_message(query.message, report_html, reply_markup=_get_services_keyboard())
        elif data == "srv:heal":
            await safe_edit_message(query.message, "🩹 <i>Auto-healing des services en cours...</i>")
            _, report_html, healed = await check_and_heal_services(auto_heal=True)
            notice = "\n\n<i>(Relance terminée)</i>" if healed else "\n\n<i>(Tous les services sont opérationnels)</i>"
            await safe_edit_message(query.message, report_html + notice, reply_markup=_get_services_keyboard())
        elif data.startswith("srv:restart:"):
            srv = data.split(":")[2]
            ok, msg = await restart_service(srv)
            _, report_html, _ = await check_and_heal_services(auto_heal=False)
            await safe_edit_message(
                query.message,
                f"{'✅' if ok else '❌'} {h(msg)}\n\n{report_html}",
                reply_markup=_get_services_keyboard(),
            )
        return

    if data.startswith("autoheal:"):
        if data == "autoheal:menu":
            await query.answer()
            await safe_edit_message(
                query.message,
                log_scanner.get_dashboard_text(),
                reply_markup=log_scanner.get_dashboard_keyboard(),
            )
        elif data == "autoheal:toggle_global":
            await query.answer()
            log_scanner.toggle_global()
            await safe_edit_message(
                query.message,
                log_scanner.get_dashboard_text(),
                reply_markup=log_scanner.get_dashboard_keyboard(),
            )
        elif data.startswith("autoheal:toggle:"):
            await query.answer()
            s_key = data.split(":", 2)[2]
            log_scanner.toggle_service(s_key)
            await safe_edit_message(
                query.message,
                log_scanner.get_dashboard_text(),
                reply_markup=log_scanner.get_dashboard_keyboard(),
            )
        elif data == "autoheal:scan_now":
            await query.answer("🔍 Scan des logs en cours...")
            issues = await log_scanner.scan_all_services()
            if not issues:
                await query.answer("✅ Aucune erreur critique détectée !", show_alert=True)
            else:
                asyncio.create_task(log_scanner.perform_scheduled_scan())
            await safe_edit_message(
                query.message,
                log_scanner.get_dashboard_text(),
                reply_markup=log_scanner.get_dashboard_keyboard(),
            )
        elif data == "autoheal:history":
            await query.answer()
            history = log_scanner.incidents_history
            if not history:
                msg = "📜 <b>Historique des Incidents :</b>\n\n<i>Aucun incident enregistré récemment.</i>"
            else:
                lines = ["📜 <b>Derniers Incidents & Interventions IA :</b>\n"]
                for inc in reversed(history[-8:]):
                    lines.append(f"• <b>{h(inc.get('name', 'Service'))}</b> ({inc.get('timestamp')}) :")
                    lines.append(f"  <code>{h(inc.get('error_snippet', '')[:140])}...</code>\n")
                msg = "\n".join(lines)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Retour Auto-Heal", callback_data="autoheal:menu")],
                [InlineKeyboardButton("❌ Fermer", callback_data="close_menu")],
            ])
            await safe_edit_message(query.message, msg, reply_markup=kb)
        return


# =============================================================================
# Interactive Admin Input Handler (Settings Prompts)
# =============================================================================

async def _handle_pending_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    uid = update.effective_user.id
    state = pending_admin_input.pop(uid, None)
    if not state:
        return False

    if state == "ws_change":
        p = Path(text.strip()).expanduser()
        if not p.exists() or not p.is_dir():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Impossible d'accéder ou de créer le dossier <code>{h(text)}</code> : {h(str(e))}",
                    reply_markup=get_workspace_keyboard(settings),
                    parse_mode=PM,
                )
                return True
        settings["workspace_dir"] = str(p.resolve())
        save_settings(settings)
        await update.message.reply_text(
            f"✅ <b>Workspace principal mis à jour :</b>\n<code>{h(settings['workspace_dir'])}</code>",
            reply_markup=get_workspace_keyboard(settings),
            parse_mode=PM,
        )
        return True

    if state == "ws_add_extra":
        p = Path(text.strip()).expanduser()
        if not p.exists() or not p.is_dir():
            await update.message.reply_text(
                f"❌ Dossier introuvable : <code>{h(text)}</code>",
                reply_markup=get_workspace_keyboard(settings),
                parse_mode=PM,
            )
            return True
        resolved = str(p.resolve())
        extra = settings.get("extra_dirs", []) or []
        if resolved not in extra:
            extra.append(resolved)
        settings["extra_dirs"] = extra
        save_settings(settings)
        await update.message.reply_text(
            f"✅ <b>Dossier secondaire ajouté (<code>--add-dir</code>) :</b>\n<code>{h(resolved)}</code>",
            reply_markup=get_workspace_keyboard(settings),
            parse_mode=PM,
        )
        return True

    if state == "persona_name":
        new_name = text.strip()[:50]
        if new_name:
            settings["agent_name"] = new_name
            save_settings(settings)
        await update.message.reply_text(
            f"✅ <b>Nom de l'agent défini sur :</b> <code>{h(settings['agent_name'])}</code>",
            reply_markup=get_persona_keyboard(settings),
            parse_mode=PM,
        )
        return True

    if state == "persona_instr":
        settings["custom_instructions"] = text.strip()
        save_settings(settings)
        runner.reset_session()  # Reset session so new system prompt takes effect immediately
        await update.message.reply_text(
            "✅ <b>Instructions personnalisées enregistrées et activées !</b>",
            reply_markup=get_persona_keyboard(settings),
            parse_mode=PM,
        )
        return True

    if state == "mcp_add":
        parts = text.strip().split()
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Format attendu : <code>&lt;nom&gt; &lt;commande_ou_url&gt;</code>",
                parse_mode=PM,
            )
            return True
        rc, out, err = await run_agy_subcommand(["mcp", "add"] + parts, timeout=15.0)
        servers = await list_mcp_servers()
        await update.message.reply_text(
            f"{'✅' if rc == 0 else '⚠️'} <code>{h(out or err or 'Serveur MCP ajouté.')}</code>",
            reply_markup=get_mcp_keyboard(servers),
            parse_mode=PM,
        )
        return True

    if state == "plugin_install":
        target = text.strip()
        ok, msg = await run_plugin_action("install", target)
        raw_txt, plugins = await list_cli_plugins()
        await update.message.reply_text(
            f"{'✅' if ok else '⚠️'} <b>Installation Plugin :</b> <code>{h(msg)}</code>\n\n<pre>{h(raw_txt[:1000])}</pre>",
            reply_markup=get_plugins_keyboard(plugins),
            parse_mode=PM,
        )
        return True

    return False


# =============================================================================
# Incoming Message & Multimedia Handlers (Text, Photo, Video, Audio, Voice, Doc)
# =============================================================================

async def handle_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    prompt = update.message.text.strip() if update.message and update.message.text else ""
    if not prompt:
        return

    if is_admin(uid, user):
        if await _handle_pending_admin_input(update, context, prompt):
            return

        if prompt.startswith("/"):
            parts = prompt.split(maxsplit=1)
            cmd_raw = parts[0][1:].split("@")[0].lower()
            cmd_args = parts[1] if len(parts) > 1 else ""
            norm_cmd = command_mgr.normalize_name(cmd_raw)
            if norm_cmd in command_mgr.list_commands():
                await dispatch_custom_command(update, context, norm_cmd, cmd_args)
                return
        await _process_user_turn(update, context, prompt)
        return

    u_info = auth_mgr.get_user(uid)
    if u_info and u_info.get("role") == ROLE_PENDING:
        await update.message.reply_text(
            "⏳ <b>Demande en cours d'examen</b>\n\n"
            "Votre demande d'accès a été transmise à l'administrateur.",
            parse_mode=PM,
        )
        return

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📨 Demander l'accès", callback_data="guest_req:ask")]])
    await update.message.reply_text(
        "👋 <b>Bonjour !</b>\n\nCe bot Antigravity est privé. Cliquez ci-dessous pour demander un accès :",
        reply_markup=kb,
        parse_mode=PM,
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ L'envoi d'images est réservé à l'administrateur.")
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    tmp_path = TEMP_DIR / f"photo_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(tmp_path))
    caption = update.message.caption or "Analyse cette image et réponds à ma demande."
    prompt = (
        f"[IMAGE FOURNIE PAR L'UTILISATEUR]\n"
        f"Chemin local de l'image : `{tmp_path.resolve()}` (Dimensions: {photo.width}x{photo.height})\n"
        f"Utilise ton outil `view_file` sur `{tmp_path.resolve()}` pour voir et analyser l'image.\n\n"
        f" Instructions / Légende de l'utilisateur :\n{caption}"
    )
    await _process_user_turn(
        update,
        context,
        prompt,
        header=f"📸 <i>Image reçue ({photo.width}×{photo.height})</i>\n\n",
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ L'envoi de vidéos est réservé à l'administrateur.")
        return
    vid = update.message.video or update.message.animation or update.message.video_note
    if not vid:
        return
    file = await vid.get_file()
    ext = ".gif" if update.message.animation else ".mp4"
    orig_name = getattr(vid, "file_name", None) or f"video_{vid.file_unique_id}{ext}"
    safe_name = re.sub(r"[^\w.\-]", "_", orig_name)
    tmp_path = TEMP_DIR / safe_name
    await file.download_to_drive(str(tmp_path))
    caption = update.message.caption or "Analyse ou traite cette vidéo."
    prompt = (
        f"[VIDÉO / ANIMATION FOURNIE PAR L'UTILISATEUR]\n"
        f"Chemin local du fichier vidéo : `{tmp_path.resolve()}`\n"
        f"Tu peux l'inspecter avec `view_file` ou la traiter avec `ffmpeg` / Python.\n\n"
        f"Instructions / Légende de l'utilisateur :\n{caption}"
    )
    await _process_user_turn(
        update,
        context,
        prompt,
        header=f"🎬 <i>Vidéo reçue : <code>{h(safe_name)}</code></i>\n\n",
    )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ L'envoi d'audios est réservé à l'administrateur.")
        return
    media = update.message.voice or update.message.audio
    if not media:
        return
    file = await media.get_file()
    is_voice = bool(update.message.voice)
    ext = ".ogg" if is_voice else (Path(getattr(media, "file_name", "") or "").suffix or ".mp3")
    orig_name = getattr(media, "file_name", None) or f"audio_{media.file_unique_id}{ext}"
    safe_name = re.sub(r"[^\w.\-]", "_", orig_name)
    tmp_path = TEMP_DIR / safe_name
    await file.download_to_drive(str(tmp_path))
    caption = update.message.caption or "Écoute, transcris ou traite ce fichier audio et réponds à la demande."
    prompt = (
        f"[{'MESSAGE VOCAL' if is_voice else 'FICHIER AUDIO'} FOURNI PAR L'UTILISATEUR]\n"
        f"Chemin local du fichier audio : `{tmp_path.resolve()}`\n"
        f"Tu peux l'écouter/analyser directement avec `view_file` sur `{tmp_path.resolve()}` ou le traiter avec Python/ffmpeg.\n\n"
        f"Instructions :\n{caption}"
    )
    icon = "🎙️" if is_voice else "🎵"
    await _process_user_turn(
        update,
        context,
        prompt,
        header=f"{icon} <i>Audio reçu : <code>{h(safe_name)}</code></i>\n\n",
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ L'envoi de documents est réservé à l'administrateur.")
        return
    doc = update.message.document
    fname = doc.file_name or f"document_{doc.file_unique_id}"
    safe_name = re.sub(r"[^\w.\- ()]", "_", fname)
    file = await doc.get_file()

    dest_path = TEMP_DIR / safe_name
    await file.download_to_drive(str(dest_path))

    caption = update.message.caption or f"Voici le fichier `{safe_name}`. Analyse-le et réponds à ma demande."
    prompt = (
        f"[DOCUMENT / FICHIER FOURNI PAR L'UTILISATEUR]\n"
        f"Nom : `{safe_name}`\n"
        f"Chemin local : `{dest_path.resolve()}`\n\n"
        f"Instructions / Légende de l'utilisateur :\n{caption}"
    )
    await _process_user_turn(
        update,
        context,
        prompt,
        header=f"📄 <i>Fichier reçu : <code>{h(safe_name)}</code></i>\n\n",
    )


# =============================================================================
# Outgoing Multimedia & Deliverable Extractor
# =============================================================================

MEDIA_AND_DOC_EXT_PATTERN = (
    r"pdf|png|jpg|jpeg|webp|gif|mp4|mov|m4v|webm|mkv|mp3|m4a|wav|flac|ogg|opus|"
    r"zip|tar\.gz|7z|rar|docx|xlsx|pptx|csv|json|html|py|sh|ps1|bat|md|txt"
)


def _extract_file_paths(text: str) -> List[str]:
    """
    Extract valid local file paths mentioned in the agent's response across Windows and Linux.
    """
    if not text:
        return []

    candidates: List[str] = []

    # 1. File URLs file:///...
    for m in re.findall(r"file:///([^\s\)\"'<>`]+)", text):
        candidates.append(m)

    # 2. Windows absolute paths (e.g. C:\Users\...\file.ext or C:/Users/.../file.ext)
    win_pat = rf"[a-zA-Z]:[\\/][^\s\)\"'<>`:*?|]+\.(?:{MEDIA_AND_DOC_EXT_PATTERN})\b"
    for m in re.findall(win_pat, text, flags=re.IGNORECASE):
        candidates.append(m)

    # 3. Unix absolute paths (e.g. /root/..., /tmp/..., /home/..., /opt/...)
    unix_pat = rf"/(?:root|opt|tmp|var|home|Users|mnt|srv)/[^\s\)\"'<>`]+\.(?:{MEDIA_AND_DOC_EXT_PATTERN})\b"
    for m in re.findall(unix_pat, text, flags=re.IGNORECASE):
        candidates.append(m)

    # 4. Backtick-enclosed paths
    for m in re.findall(r"`([^`\n]+\.(?:" + MEDIA_AND_DOC_EXT_PATTERN + r"))`", text, flags=re.IGNORECASE):
        candidates.append(m.strip())

    ws_dir = Path(settings.get("workspace_dir", str(config.WORKSPACE_DIR)))
    valid_files: List[str] = []

    # Core source files of the bot itself that shouldn't be auto-sent just because they were mentioned
    bot_core_files = {
        str((BASE_DIR / f).resolve())
        for f in (
            "bot.py", "agent_runner.py", "config.py", "ui_helpers.py", "auth_manager.py",
            "command_manager.py", "memory_manager.py", "mem.py", "setup_wizard.py", "updater.py",
            "server_watchdog.py", "log_scanner.py", "tg_send.py", "browser_tool.py",
            "requirements.txt", "settings.json", "users.json", "custom_commands.json", "VERSION.json",
        )
    }

    for raw in candidates:
        cleaned = raw.strip().rstrip(".,;:!)")
        for base in (None, ws_dir, BASE_DIR, TEMP_DIR):
            try:
                p = Path(cleaned) if base is None else (base / cleaned)
                if p.is_file() and p.stat().st_size > 0:
                    resolved = str(p.resolve())
                    if resolved not in bot_core_files and resolved not in valid_files:
                        valid_files.append(resolved)
                    break
            except Exception:
                continue

    return valid_files


async def _send_single_deliverable(bot, chat_id: int, fp: str, reply_to_msg=None) -> bool:
    """
    Send a generated file to Telegram using the appropriate native media method
    (Photo, Video, Audio, Voice, Animation, or Document).
    """
    p = Path(fp)
    if not p.is_file() or p.stat().st_size == 0:
        return False

    file_size_mb = p.stat().st_size / (1024 * 1024)
    fname = p.name
    ext = p.suffix.lower()

    if file_size_mb > 49.5:
        return False

    caption = f"📁 <b>{h(fname)}</b> (<code>{file_size_mb:.2f} Mo</code>)" if file_size_mb >= 0.1 else f"📁 <b>{h(fname)}</b>"

    try:
        with open(p, "rb") as f:
            inp = InputFile(f, filename=fname)
            if ext in PHOTO_EXTS and file_size_mb <= 10.0:
                await bot.send_photo(chat_id=chat_id, photo=inp, caption=f"🖼️ <b>{h(fname)}</b>", parse_mode=PM)
                return True
            if ext in VIDEO_EXTS:
                await bot.send_video(
                    chat_id=chat_id,
                    video=inp,
                    caption=f"🎬 <b>{h(fname)}</b>",
                    supports_streaming=True,
                    parse_mode=PM,
                )
                return True
            if ext in AUDIO_EXTS:
                await bot.send_audio(chat_id=chat_id, audio=inp, caption=f"🎵 <b>{h(fname)}</b>", parse_mode=PM)
                return True
            if ext in VOICE_EXTS:
                await bot.send_voice(chat_id=chat_id, voice=inp, caption=f"🎙️ <b>{h(fname)}</b>", parse_mode=PM)
                return True
            if ext in ANIM_EXTS:
                await bot.send_animation(chat_id=chat_id, animation=inp, caption=f"🎞️ <b>{h(fname)}</b>", parse_mode=PM)
                return True
            await bot.send_document(chat_id=chat_id, document=inp, caption=caption, parse_mode=PM)
            return True
    except Exception as e:
        logger.warning(f"Primary media send failed for {fname} ({e}), retrying as generic document...")
        try:
            with open(p, "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(f, filename=fname),
                    caption=caption,
                    parse_mode=PM,
                )
                return True
        except Exception as e2:
            logger.warning(f"Document fallback also failed for {fname}: {e2}")
            return False


# =============================================================================
# Core Turn Execution Engine (Queued, Streaming, Crash-Proof)
# =============================================================================

async def _process_user_turn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    header: str = "",
    custom_settings: Optional[dict] = None,
):
    chat_id = update.effective_chat.id

    # If another turn is currently running, notify the user that their message is queued
    queued_notice_msg = None
    if turn_execution_lock.locked():
        abort_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Interrompre la tâche en cours", callback_data="abort_running")]
        ])
        try:
            queued_notice_msg = await update.message.reply_text(
                "📥 <b>Message mis en file d'attente.</b>\n"
                "<i>Il sera traité automatiquement dès que la tâche actuelle se termine.</i>",
                reply_markup=abort_kb,
                parse_mode=PM,
            )
        except Exception:
            pass

    async with turn_execution_lock:
        if queued_notice_msg:
            try:
                await queued_notice_msg.delete()
            except Exception:
                pass

        try:
            TRANSIENT_MSGS_FILE.unlink(missing_ok=True)
            TURN_SENT_FILES_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        active_settings = custom_settings if custom_settings is not None else settings
        agent_name = active_settings.get("agent_name", "Antigravity Agent")
        verbosity = active_settings.get("verbosity", "normal")

        abort_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Stopper l'exécution", callback_data="abort_running")]
        ])

        live_msg = None
        try:
            init_text = (
                f"{header}⏳ <b>{h(agent_name)} prépare l'action...</b>"
                if header
                else f"⏳ <b>{h(agent_name)} prépare l'action...</b>"
            )
            live_msg = await update.message.reply_text(init_text, reply_markup=abort_kb, parse_mode=PM)
        except Exception:
            try:
                live_msg = await update.message.reply_text(f"⏳ {agent_name} prépare l'action...")
            except Exception as e:
                logger.warning(f"Failed sending initial ack: {e}")

        typing_active = True

        async def keep_typing():
            while typing_active:
                try:
                    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
                except Exception:
                    pass
                await asyncio.sleep(4.0)

        typing_task = asyncio.create_task(keep_typing())

        last_rendered = ""
        tool_blocks: List[tuple] = []
        tool_start_times: Dict[str, float] = {}
        start_time = asyncio.get_event_loop().time()

        async def on_update(current_text: str, current_action: str):
            nonlocal live_msg, last_rendered
            if not current_text and not current_action and not tool_blocks:
                return

            parts = []
            if header:
                parts.append(header)

            if verbosity != "compact" and tool_blocks:
                max_blocks = 6 if verbosity == "detailed" else 3
                parts.extend(blk for _, blk in tool_blocks[-max_blocks:])

            if current_action:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                spinner = _next_spinner()
                time_str = f" <code>{elapsed}s</code>" if elapsed >= 4 else ""
                parts.append(f"{spinner} <b>En cours :</b> <i>{h(current_action)}</i>{time_str}")
            elif not current_text:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                spinner = _next_spinner()
                time_str = f" <code>{elapsed}s</code>" if elapsed >= 3 else ""
                parts.append(f"{spinner} <i>Traitement en cours...{time_str}</i>")

            if current_text:
                converted = sanitize_telegram_html(md_to_html(current_text))
                parts.append(converted + " <code>▌</code>")

            display = "\n\n".join(parts)
            if display != last_rendered and live_msg:
                updated = await safe_edit_message(live_msg, display, reply_markup=abort_kb)
                if updated:
                    last_rendered = display

        async def on_model_fallback(old_model: str, new_model: str):
            notice = (
                f"{header}<blockquote>⚠️ Quota <code>{h(old_model)}</code> atteint, "
                f"bascule automatique sur <code>{h(new_model)}</code>...</blockquote>"
            )
            if live_msg:
                await safe_edit_message(live_msg, notice, reply_markup=abort_kb)

        async def on_tool_call(tool_name: str, args: dict, call_id: str):
            block = format_tool_call_html(tool_name, args, result=None)
            tool_blocks.append((call_id, block))
            tool_start_times[call_id] = asyncio.get_event_loop().time()

        async def on_tool_result(tool_name: str, args: dict, result: str, call_id: str, is_error: bool):
            elapsed = ""
            if call_id in tool_start_times:
                secs = int(asyncio.get_event_loop().time() - tool_start_times.pop(call_id))
                elapsed = f" [{secs}s]" if secs >= 2 else ""
            result_with_time = f"{result}{elapsed}" if elapsed and result else result
            block = format_tool_call_html(tool_name, args, result=result_with_time, is_error=is_error)
            for i, (cid, _) in enumerate(tool_blocks):
                if cid == call_id:
                    tool_blocks[i] = (call_id, block)
                    return
            tool_blocks.append((call_id, block))

        response_text = ""
        is_success = False
        try:
            response_text, is_success = await runner.run_prompt_stream(
                prompt=prompt,
                settings=active_settings,
                on_update=on_update,
                on_model_fallback=on_model_fallback,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )
        except Exception as e:
            logger.error(f"Error during agent execution: {e}")
            response_text = f"❌ <b>Erreur inattendue :</b> <code>{h(str(e))}</code>"
            is_success = False
        finally:
            typing_active = False
            typing_task.cancel()

        # --- Final Response Rendering ---
        try:
            final_parts = []
            if header:
                final_parts.append(header)
            if verbosity == "detailed" and tool_blocks:
                final_parts.extend(blk for _, blk in tool_blocks[-8:])
            if is_success:
                final_parts.append(sanitize_telegram_html(md_to_html(response_text)))
            else:
                final_parts.append(sanitize_telegram_html(response_text))
            final_html = "\n\n".join(final_parts).strip()

            chunks = smart_split_html(final_html)

            if live_msg:
                await safe_edit_message(live_msg, chunks[0], reply_markup=None)
            else:
                live_msg = await safe_reply_message(update.message, chunks[0])

            for chunk in chunks[1:]:
                await safe_reply_message(update.message, chunk)

            # Purge transient status messages sent via tg_send during this turn
            if TRANSIENT_MSGS_FILE.exists():
                try:
                    with open(TRANSIENT_MSGS_FILE, "r", encoding="utf-8") as tf:
                        transient_ids = json.load(tf)
                    for tid in transient_ids:
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=tid)
                        except Exception:
                            pass
                    TRANSIENT_MSGS_FILE.unlink(missing_ok=True)
                except Exception as e:
                    logger.debug(f"Failed cleaning transient messages: {e}")

        except Exception as e:
            logger.error(f"Error rendering final response: {e}")
            try:
                plain = strip_all_html(response_text)[:4000]
                if live_msg:
                    await live_msg.edit_text(plain)
                else:
                    await update.message.reply_text(plain)
            except Exception:
                pass

        # --- Automatic Delivery of Generated Files (Photos, Videos, Audio, Documents) ---
        if is_success and active_settings.get("auto_send_files", True):
            try:
                already_sent = set()
                if TURN_SENT_FILES_FILE.exists():
                    try:
                        already_sent = set(json.loads(TURN_SENT_FILES_FILE.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                    TURN_SENT_FILES_FILE.unlink(missing_ok=True)

                file_paths = _extract_file_paths(response_text)
                for fp in file_paths:
                    if str(Path(fp).resolve()) in already_sent:
                        continue
                    await _send_single_deliverable(context.bot, chat_id, fp, reply_to_msg=update.message)
            except Exception as e:
                logger.warning(f"File delivery loop warning: {e}")


# =============================================================================
# Autonomous Auto-Heal Worker
# =============================================================================

async def trigger_auto_heal_agent(
    service_key: str,
    service_name: str,
    error_snippet: str,
    application,
):
    if runner.is_running or turn_execution_lock.locked():
        return

    chat_id = auth_mgr.get_primary_admin_id()
    if not chat_id:
        return

    header = (
        f"🚨 <b>Auto-Heal IA : Incident Détecté sur {h(service_name)} !</b>\n\n"
        f"📋 <b>Erreur récente dans les logs :</b>\n"
        f"<code>{h(error_snippet[:350])}</code>\n\n"
    )

    live_msg = None
    try:
        live_msg = await application.bot.send_message(
            chat_id=chat_id,
            text=f"{header}🤖 <b>Analyse du problème et auto-réparation en cours...</b>",
            parse_mode=PM,
        )
    except Exception:
        return

    prompt = (
        f"[INCIDENT SYSTÈME DÉTECTÉ PAR LE SCANNER DE LOGS]\n"
        f"Le service '{service_name}' ({service_key}) a rencontré une erreur critique :\n"
        f"```\n{error_snippet}\n```\n\n"
        f"MISSION D'AUTO-RÉPARATION AUTONOME :\n"
        f"1. Examine les logs et vérifie l'état actuel du service.\n"
        f"2. Identifie la cause exacte et applique la correction ou le redémarrage approprié.\n"
        f"3. Vérifie que le service est à nouveau opérationnel et rédige un rapport concis."
    )

    async with turn_execution_lock:
        response_text, is_success = await runner.run_prompt_stream(
            prompt=prompt,
            settings=settings,
        )
        final_parts = [header]
        if is_success:
            final_parts.append(sanitize_telegram_html(md_to_html(response_text)))
        else:
            final_parts.append(sanitize_telegram_html(response_text))
        final_html = "\n\n".join(final_parts).strip()

        chunks = smart_split_html(final_html)
        if live_msg:
            await safe_edit_message(live_msg, chunks[0])
        for chunk in chunks[1:]:
            try:
                await application.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=PM)
            except Exception:
                pass


async def auto_heal_background_worker():
    logger.info("Démarrage du worker d'arrière-plan Auto-Heal...")
    await asyncio.sleep(45)
    while True:
        try:
            if not runner.is_running and log_scanner.is_global_enabled():
                await log_scanner.perform_scheduled_scan()
        except Exception as e:
            logger.warning(f"Exception dans auto_heal_background_worker : {e}")
        interval = int(log_scanner.config.get("scan_interval_seconds", 60))
        await asyncio.sleep(max(30, interval))


async def auto_update_watcher_worker(application):
    """
    Background worker that checks the GitHub repository every 10 minutes.
    When a new push/commit or required Antigravity CLI update is detected,
    sends an interactive notification to the Administrator on Telegram asking if they want to update.
    """
    logger.info("Démarrage du worker de surveillance des mises à jour GitHub (Auto-Update Watcher)...")
    await asyncio.sleep(60)
    while True:
        try:
            if not runner.is_running:
                admin_id = auth_mgr.get_primary_admin_id()
                if admin_id:
                    info = await check_for_updates()
                    if info.get("ok") and info.get("update_available"):
                        remote_sha_full = info.get("remote_sha_full", "")
                        if should_notify_for_commit(remote_sha_full):
                            mark_commit_notified(remote_sha_full)
                            alert_html = format_update_check_html(info, is_push_alert=True)
                            kb = get_update_prompt_keyboard(info)
                            await application.bot.send_message(
                                chat_id=admin_id,
                                text=alert_html,
                                reply_markup=kb,
                                parse_mode=PM,
                            )
        except Exception as e:
            logger.debug(f"Auto-update watcher check warning: {e}")
        await asyncio.sleep(600)


async def handle_dynamic_command_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_user):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur.")
        return
    raw_text = update.message.text or ""
    parts = raw_text.strip().split(maxsplit=1)
    cmd_raw = parts[0].lstrip("/").split("@")[0].lower()
    norm_cmd = command_mgr.normalize_name(cmd_raw)
    args_text = parts[1] if len(parts) > 1 else ""

    if norm_cmd in command_mgr.list_commands():
        await dispatch_custom_command(update, context, norm_cmd, args_text)
    else:
        await update.message.reply_text(
            f"❓ Commande inconnue : <code>/{h(cmd_raw)}</code>\n"
            f"Tapez <code>/help</code> pour le guide ou <code>/settings</code> pour le Centre de Contrôle.",
            parse_mode=PM,
        )


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("\n⚠️  TELEGRAM_BOT_TOKEN manquant dans le fichier .env !")
        print("👉 Lancement automatique de l'assistant de configuration interactif (setup_wizard.py)...\n")
        try:
            import setup_wizard
            setup_wizard.run_wizard()
            # Reload config after wizard completes
            from dotenv import load_dotenv
            load_dotenv(config.ENV_FILE, override=True)
            config.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            token = config.TELEGRAM_BOT_TOKEN
        except Exception as e:
            logger.error(f"Impossible de lancer setup_wizard: {e}")

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN toujours manquant. Exécutez `python setup_wizard.py`.")
        sys.exit(1)

    logger.info("Démarrage Antigravity Telegram Bot v4.1 (Universal Windows/Linux, Multi-Agent, Auto-Update)...")
    t_request = HTTPXRequest(
        connection_pool_size=20,
        read_timeout=45.0,
        write_timeout=45.0,
        connect_timeout=30.0,
    )
    app = (
        ApplicationBuilder()
        .token(token)
        .request(t_request)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(global_error_handler)

    # Built-in system command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("models", cmd_models))
    app.add_handler(CommandHandler("effort", cmd_effort))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("mcp", cmd_mcp))
    app.add_handler(CommandHandler("plugins", cmd_plugins))
    app.add_handler(CommandHandler("skill", cmd_plugins))
    app.add_handler(CommandHandler("remote", cmd_remote))
    app.add_handler(CommandHandler("workspace", cmd_workspace))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("update_cli", cmd_update_cli))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("mem", cmd_memory))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("abort", cmd_abort))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("autoheal", cmd_autoheal))

    # Pre-register built-in custom commands (/goal, /grill_me, /plan, /boost, /teamwork, etc.)
    for c_name in list(command_mgr.list_commands().keys()):
        def _make_handler(name_to_bind):
            async def _h(u: Update, c: ContextTypes.DEFAULT_TYPE):
                user_args = " ".join(c.args or [])
                await dispatch_custom_command(u, c, name_to_bind, user_args)
            return _h
        app.add_handler(CommandHandler(c_name, _make_handler(c_name)))

    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt_message))
    app.add_handler(MessageHandler(filters.COMMAND, handle_dynamic_command_fallback))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()