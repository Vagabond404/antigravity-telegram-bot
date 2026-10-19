"""
i18n.py - Universal Internationalization & Language Localization Engine
Supports English ('en', default) and French ('fr'), with automatic language detection,
per-user language preferences, and full translation dictionaries for all system messages.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("i18n")

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ["en", "fr"]

# In-memory user language cache {user_id: "en" | "fr"}
_user_languages: Dict[int, str] = {}

# Common French linguistic markers for dynamic auto-detection
FRENCH_MARKERS = [
    r"\bbonjour\b", r"\bsalut\b", r"\bmerci\b", r"\bs'il\s+te\s+pla[iî]t\b", r"\bsvp\b",
    r"\bc'est\b", r"\bj'ai\b", r"\bqu'est-ce\b", r"\bcomment\b", r"\bpourquoi\b",
    r"\bfaire\b", r"\bfais\b", r"\bpeux-tu\b", r"\baide-moi\b", r"\bje\s+veux\b",
    r"\bdevoirs?\b", r"\bcours\b", r"\bécole\b", r"\bprof\b", r"\bgroupe\b",
    r"\bparamètres?\b", r"\bactiver\b", r"\bdésactiver\b", r"\bmettre\s+à\s+jour\b",
    r"\bquitter\b", r"\bsilencieux\b", r"\bécoute\b", r"\brépondre\b", r"\brésumé\b",
    r"\bavec\b", r"\bpour\b", r"\bdans\b", r"\bsur\b", r"\bune?\b", r"\bdes\b", r"\bqui\b",
]

# Common English linguistic markers
ENGLISH_MARKERS = [
    r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bthanks\b", r"\bplease\b",
    r"\bwhat\b", r"\bhow\b", r"\bwhy\b", r"\bcan\s+you\b", r"\bhelp\s+me\b",
    r"\bi\s+want\b", r"\bhomework\b", r"\blesson\b", r"\bschool\b", r"\bteacher\b",
    r"\bgroup\b", r"\bsettings\b", r"\benable\b", r"\bdisable\b", r"\bupdate\b",
    r"\bleave\b", r"\bsilent\b", r"\blisten\b", r"\breply\b", r"\bsummarize\b",
    r"\bwith\b", r"\bfor\b", r"\bin\b", r"\bon\b", r"\bthe\b", r"\bthis\b",
]

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # General & Auth
    "cmd_admin_only": {
        "en": "⛔ This command is reserved for the administrator.",
        "fr": "⛔ Cette commande est réservée à l'administrateur.",
    },
    "unknown_command": {
        "en": "❓ Unknown command: <code>/{cmd}</code>\nType <code>/help</code> for the guide or <code>/settings</code> for the Control Center.",
        "fr": "❓ Commande inconnue : <code>/{cmd}</code>\nTapez <code>/help</code> pour le guide ou <code>/settings</code> pour le Centre de Contrôle.",
    },
    "guest_welcome": {
        "en": "👋 Hello {name}!\n\n🔒 This Antigravity bot is private. Click below to request access from the administrator:",
        "fr": "👋 Bonjour {name} !\n\n🔒 Ce bot Antigravity est privé. Cliquez ci-dessous pour demander un accès à l'administrateur :",
    },
    "guest_request_sent": {
        "en": "⏳ <b>Request Pending</b>\n\nYour access request has been sent to the administrator.",
        "fr": "⏳ <b>Demande en cours d'examen</b>\n\nVotre demande d'accès a été transmise à l'administrateur.",
    },
    "guest_request_btn": {
        "en": "📨 Request Access",
        "fr": "📨 Demander l'accès",
    },

    # Start & Claim
    "admin_claim_banner": {
        "en": "🎉 <b>Initial Setup Complete!</b>\nYour account (<code>{uid}</code>) has been registered as the <b>Primary Administrator</b>.\n\n",
        "fr": "🎉 <b>Configuration Initiale Réussie !</b>\nVotre compte (<code>{uid}</code>) a été enregistré comme <b>Administrateur Principal</b>.\n\n",
    },
    "welcome_admin": {
        "en": (
            "👋 <b>Welcome to {agent_name} (Antigravity CLI v4.2)!</b>\n\n"
            "Your universal, autonomous AI gateway powered by the latest <b>Google Antigravity CLI</b>.\n\n"
            "⚡ <b>Core Capabilities:</b>\n"
            "• 🧠 <b>Dynamic Models & Effort:</b> Real-time CLI models & deep thinking (<code>/settings</code>, <code>/models</code>, <code>/effort</code>)\n"
            "• 🤝 <b>Multi-Agent Swarm:</b> Coordinated parallel subagents (<code>/agents</code>, <code>/teamwork</code>)\n"
            "• 📤 <b>Full Multimedia:</b> Send & receive photos, videos, audio, voice notes, PDFs & archives\n"
            "• 🔌 <b>CLI Ecosystem:</b> 1-click management of <code>/mcp</code> servers, <code>/plugins</code>, <code>/remote</code>, and <code>/sessions</code>\n"
            "• 🧠 <b>Long-Term Memory:</b> Local vector memory across conversations (<code>/memory</code>, <code>/remember</code>, <code>/forget</code>)\n"
            "• 🏫 <b>Autonomous Group Intelligence:</b> Stealth observation, custom missions, summaries & interactive assistance (<code>/groups</code>)\n\n"
            "💡 <i>Send a message, a photo, a document or type <code>/settings</code> to customize everything!</i>"
        ),
        "fr": (
            "👋 <b>Bienvenue sur {agent_name} (Antigravity CLI v4.2) !</b>\n\n"
            "Votre passerelle IA autonome universelle propulsée par la dernière version de <b>Google Antigravity CLI</b>.\n\n"
            "⚡ <b>Capacités Intégrées :</b>\n"
            "• 🧠 <b>Modèles & Effort Dynamiques :</b> Sélection en direct depuis <code>agy models</code> et effort jusqu'à <code>xhigh</code>/<code>max</code> (<code>/settings</code>, <code>/models</code>, <code>/effort</code>)\n"
            "• 🤝 <b>Essaim Multi-Agents :</b> Orchestration parallèle de sous-agents autonomes (<code>/agents</code>, <code>/teamwork</code>)\n"
            "• 📤 <b>Multimédia Complet :</b> Envoyez et recevez images, vidéos, audios, vocaux, PDF et archives\n"
            "• 🔌 <b>Écosystème CLI :</b> Gestion en 1 clic des serveurs <code>/mcp</code>, <code>/plugins</code>, <code>/remote</code> et <code>/sessions</code>\n"
            "• 🧠 <b>Mémoire Long-Terme :</b> Mémoire vectorielle locale inter-conversations (<code>/memory</code>, <code>/remember</code>, <code>/forget</code>)\n"
            "• 🏫 <b>Intelligence de Groupe Autonome :</b> Écoute furtive, missions personnalisées, résumés & assistance (<code>/groups</code>)\n\n"
            "💡 <i>Envoyez un message, une photo, un fichier ou tapez <code>/settings</code> pour tout personnaliser !</i>"
        ),
    },

    # Help
    "help_title": {
        "en": "📚 <b>Complete Guide — Antigravity Telegram Agent</b>",
        "fr": "📚 <b>Guide Complet — Antigravity Telegram Agent</b>",
    },

    # Groups & Channels
    "groups_dashboard_title": {
        "en": "🏫 <b>Telegram Groups & Channels Management</b>",
        "fr": "🏫 <b>Gestion des Groupes & Canaux Telegram</b>",
    },
    "groups_dashboard_desc": {
        "en": (
            "• <b>Registered Groups:</b> <code>{total}</code>\n"
            "• 🔇 <b>Silent Listen Mode:</b> <code>{passive}</code>\n"
            "• 💬 <b>Interactive Mode (@mentions):</b> <code>{active}</code>\n\n"
            "🛡️ <i>In Silent Listen Mode (default), the bot observes messages, logs discussions for the AI agent, "
            "and NEVER sends any messages or error notifications in the group. Click a group below to customize its mission or permissions:</i>\n\n"
            "💡 <i>Tip: The bot automatically registers any group it is in as soon as a message is posted. You can also add one manually via <code>/groups add &lt;id&gt; [Title]</code>.</i>"
        ),
        "fr": (
            "• <b>Groupes enregistrés :</b> <code>{total}</code>\n"
            "• 🔇 <b>Mode Écoute Seule (Silencieux) :</b> <code>{passive}</code>\n"
            "• 💬 <b>Mode Interactif (@mentions) :</b> <code>{active}</code>\n\n"
            "🛡️ <i>En mode Écoute Seule (par défaut), le bot observe les messages, enregistre le contexte pour l'agent IA, "
            "et n'envoie JAMAIS le moindre message ou refus d'accès dans le groupe. Cliquez sur un groupe ci-dessous pour modifier sa mission ou ses droits :</i>\n\n"
            "💡 <i>Astuce : Le bot enregistre automatiquement tout groupe dès qu'un message y est posté. Vous pouvez aussi l'ajouter avec <code>/groups add &lt;id&gt; [Titre]</code>.</i>"
        ),
    },
    "new_group_alert": {
        "en": (
            "👋 <b>New Group Discovered!</b>\n\n"
            "The bot detected and registered the group <b>{title}</b>.\n"
            "• <b>Group ID:</b> <code>{chat_id}</code>\n"
            "• <b>Current Mode:</b> 🔇 <b>Silent Listen Only</b> (100% quiet)\n"
            "• <b>Read Access:</b> ✅ Enabled\n"
            "• <b>Write Access:</b> ⛔ Disabled (Never speaks in group)\n\n"
            "🛡️ <i>The AI agent is now observing this group. You can ask the agent in private chat to summarize discussions, "
            "track announcements, or watch for specific events.</i>"
        ),
        "fr": (
            "👋 <b>Nouveau Groupe Détecté !</b>\n\n"
            "Le bot a détecté et enregistré le groupe <b>{title}</b>.\n"
            "• <b>ID Groupe :</b> <code>{chat_id}</code>\n"
            "• <b>Mode Actuel :</b> 🔇 <b>Écoute Seule (Silencieux)</b> (100% discret)\n"
            "• <b>Accès Lecture :</b> ✅ Activé\n"
            "• <b>Accès Écriture :</b> ⛔ Désactivé (Ne parle jamais dans le groupe)\n\n"
            "🛡️ <i>L'agent IA observe désormais ce groupe. Vous pouvez lui demander en privé de résumer les échanges, "
            "suivre des annonces ou surveiller des devoirs/tâches.</i>"
        ),
    },
    "group_unauthorized_alert": {
        "en": (
            "⚠️ <b>Unauthorized Group Addition Blocked!</b>\n\n"
            "User <b>{name}</b> (<code>{uid}</code>) attempted to add the bot to group:\n"
            "• <b>Title:</b> {title}\n"
            "• <b>ID:</b> <code>{chat_id}</code>\n\n"
            "🛡️ <i>The bot automatically left the group immediately to protect your privacy.</i>"
        ),
        "fr": (
            "⚠️ <b>Tentative d'Ajout Non-Autorisé Bloquée !</b>\n\n"
            "L'utilisateur <b>{name}</b> (<code>{uid}</code>) a tenté d'ajouter le bot au groupe :\n"
            "• <b>Titre :</b> {title}\n"
            "• <b>ID :</b> <code>{chat_id}</code>\n\n"
            "🛡️ <i>Le bot a immédiatement quitté le groupe pour préserver votre vie privée.</i>"
        ),
    },

    # Settings & Buttons
    "btn_refresh": {"en": "🔄 Refresh", "fr": "🔄 Actualiser"},
    "btn_settings": {"en": "⬅️ Settings", "fr": "⬅️ Paramètres"},
    "btn_close": {"en": "❌ Close", "fr": "❌ Fermer"},
    "btn_back": {"en": "⬅️ Back", "fr": "⬅️ Retour"},
    "btn_groups": {"en": "🏫 Groups (/groups)", "fr": "🏫 Groupes (/groups)"},
    "btn_language": {"en": "🌐 Language (EN / FR)", "fr": "🌐 Langue (EN / FR)"},
    "btn_update": {"en": "🔄 System Update (/update)", "fr": "🔄 Maj Système (/update)"},
    "btn_users": {"en": "👥 Users & Access", "fr": "👥 Utilisateurs & Accès"},
}


def detect_language(text: str, user_telegram_lang: Optional[str] = None) -> str:
    """
    Intelligently detect language from user prompt text or user profile code.
    Defaults to 'en' (English).
    """
    if not text or len(text.strip()) < 3:
        if user_telegram_lang and user_telegram_lang.lower().startswith("fr"):
            return "fr"
        return DEFAULT_LANGUAGE

    lower = text.lower()

    fr_matches = sum(1 for p in FRENCH_MARKERS if re.search(p, lower))
    en_matches = sum(1 for p in ENGLISH_MARKERS if re.search(p, lower))

    if fr_matches > en_matches and fr_matches >= 1:
        return "fr"
    if en_matches > fr_matches and en_matches >= 1:
        return "en"

    if user_telegram_lang and user_telegram_lang.lower().startswith("fr"):
        return "fr"
    return DEFAULT_LANGUAGE


def get_user_language(user_id: int, fallback: str = DEFAULT_LANGUAGE) -> str:
    """Get currently active language for a specific user."""
    return _user_languages.get(user_id, fallback)


def set_user_language(user_id: int, lang: str) -> None:
    """Explicitly set user's preferred language ('en' | 'fr')."""
    if lang in SUPPORTED_LANGUAGES:
        _user_languages[user_id] = lang


def detect_and_set_language(user_id: int, text: str, user_telegram_lang: Optional[str] = None) -> str:
    """Detect language from message and update user's session language preference."""
    lang = detect_language(text, user_telegram_lang)
    _user_languages[user_id] = lang
    return lang


def t(key: str, lang: Optional[str] = None, user_id: Optional[int] = None, **kwargs) -> str:
    """
    Retrieve translated string for the given key and language.
    Substitutes format arguments safely.
    """
    if not lang:
        if user_id:
            lang = get_user_language(user_id)
        else:
            lang = DEFAULT_LANGUAGE

    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get("en") or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
