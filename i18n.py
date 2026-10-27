"""
i18n.py - Universal Internationalization & Dynamic Language Localization Engine
Supports English ('en', default) and French ('fr') natively, with automatic language detection,
per-user language preferences, persistent locale storage in `locales/{lang}.json`,
and dynamic translation support for any world language.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import BASE_DIR, LOCALES_DIR

logger = logging.getLogger("i18n")

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ["en", "fr", "es", "de", "it", "pt", "ru", "ja", "zh", "ar"]

# In-memory user language cache {user_id: "en" | "fr" | ...}
_user_languages: Dict[int, str] = {}

# In-memory custom/external locale cache {lang_code: {key: text}}
_loaded_locales: Dict[str, Dict[str, str]] = {}

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

# Common Spanish linguistic markers
SPANISH_MARKERS = [
    r"\bhola\b", r"\bgracias\b", r"\bpor\s+favor\b", r"\bbuenos\s+d[ií]as\b",
    r"\bc[oó]mo\b", r"\bpor\s+qu[eé]\b", r"\bpuedes\b", r"\bayuda\b",
]

# Common German linguistic markers
GERMAN_MARKERS = [
    r"\bhallo\b", r"\bdanke\b", r"\bbitte\b", r"\bguten\s+tag\b",
    r"\bwie\b", r"\bwarum\b", r"\bkannst\s+du\b", r"\bhilfe\b",
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
            "• 📊 <b>Quota Gauges:</b> Real-time token usage breakdown for Gemini, Argon & Claude (<code>/usage</code>)\n"
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
            "• 📊 <b>Jauges de Quotas :</b> Consommation en direct des tokens Gemini, Argon & Claude (<code>/usage</code>)\n"
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

    # Settings & Buttons
    "btn_refresh": {"en": "🔄 Refresh", "fr": "🔄 Actualiser"},
    "btn_settings": {"en": "⬅️ Settings", "fr": "⬅️ Paramètres"},
    "btn_close": {"en": "❌ Close", "fr": "❌ Fermer"},
    "btn_back": {"en": "⬅️ Back", "fr": "⬅️ Retour"},
    "btn_groups": {"en": "🏫 Groups (/groups)", "fr": "🏫 Groupes (/groups)"},
    "btn_language": {"en": "🌐 Language", "fr": "🌐 Langue"},
    "btn_update": {"en": "🔄 System Update (/update)", "fr": "🔄 Maj Système (/update)"},
    "btn_users": {"en": "👥 Users & Access", "fr": "👥 Utilisateurs & Accès"},
    "btn_reset_cooldowns": {"en": "🔄 Reset Cooldown Locks", "fr": "🔄 Réinitialiser les Verrous"},
    "btn_abort": {"en": "🛑 Stop Execution", "fr": "🛑 Stopper l'exécution"},
    "btn_clear_session": {"en": "🗑️ New Conversation (/clear)", "fr": "🗑️ Nouvelle Discussion (/clear)"},
    "btn_account_tier": {"en": "🏷️ Google Plan (Free/Pro/Ultra)", "fr": "🏷️ Forfait Google (Gratuit/Pro/Ultra)"},

    # Quota & Model notices
    "quota_reached_fallback": {
        "en": "⚠️ Quota limit on <code>{old_model}</code> reached. Automatically switching to <code>{new_model}</code>...",
        "fr": "⚠️ Quota <code>{old_model}</code> atteint. Bascule automatique sur <code>{new_model}</code>...",
    },
    "quota_exhausted_all": {
        "en": (
            "💳 <b>Quota Limit Temporarily Reached</b>\n\n"
            "All candidate AI models have reached their rate limit for this rolling cycle.\n"
            "<pre>{error}</pre>\n\n"
            "💡 Type <code>/usage</code> to check your token gauges or click below to reset locks."
        ),
        "fr": (
            "💳 <b>Crédits / Quota temporairement atteints</b>\n\n"
            "Tous les modèles testés ont atteint leur limite pour ce cycle glissant.\n"
            "<pre>{error}</pre>\n\n"
            "💡 Tapez <code>/usage</code> pour voir vos jauges ou cliquez ci-dessous pour réinitialiser."
        ),
    },
    "auth_required": {
        "en": (
            "🔐 <b>Google Antigravity Authentication Required!</b>\n\n"
            "Please run <code>agy</code> via SSH or terminal on your server to complete Google login."
        ),
        "fr": (
            "🔐 <b>Authentification Google Antigravity requise sur le serveur !</b>\n\n"
            "Tapez <code>agy</code> en SSH ou terminal sur votre serveur pour vous connecter."
        ),
    },
    "exec_interrupted": {
        "en": "🛑 Execution stopped by user.",
        "fr": "🛑 Exécution interrompue par l'utilisateur.",
    },
    "action_in_progress": {
        "en": "Processing in progress...",
        "fr": "Traitement en cours...",
    },
    "analyzing": {
        "en": "🧠 Analyzing & Reasoning...",
        "fr": "🧠 Analyse & Réflexion en cours...",
    },
}


def load_locale_file(lang: str) -> Dict[str, str]:
    """Load a persistent JSON locale file from locales/{lang}.json if available."""
    if lang in _loaded_locales:
        return _loaded_locales[lang]

    loc_file = LOCALES_DIR / f"{lang}.json"
    if loc_file.is_file():
        try:
            data = json.loads(loc_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _loaded_locales[lang] = data
                return data
        except Exception as e:
            logger.warning(f"Failed to load locale file {loc_file}: {e}")

    _loaded_locales[lang] = {}
    return {}


def save_locale_file(lang: str, translations: Dict[str, str]) -> bool:
    """Save or update custom translated strings into locales/{lang}.json."""
    try:
        LOCALES_DIR.mkdir(parents=True, exist_ok=True)
        loc_file = LOCALES_DIR / f"{lang}.json"
        existing = load_locale_file(lang)
        merged = {**existing, **translations}
        loc_file.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        _loaded_locales[lang] = merged
        logger.info(f"Saved {len(merged)} translated strings to {loc_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save locale file for {lang}: {e}")
        return False


def detect_language(text: str, user_telegram_lang: Optional[str] = None) -> str:
    """
    Intelligently detect language from user prompt text or user profile code.
    Defaults to 'en' (English).
    """
    if not text or len(text.strip()) < 3:
        if user_telegram_lang:
            code = user_telegram_lang.lower().split("-")[0].split("_")[0]
            if code in SUPPORTED_LANGUAGES:
                return code
        return DEFAULT_LANGUAGE

    lower = text.lower()

    fr_matches = sum(1 for p in FRENCH_MARKERS if re.search(p, lower))
    en_matches = sum(1 for p in ENGLISH_MARKERS if re.search(p, lower))
    es_matches = sum(1 for p in SPANISH_MARKERS if re.search(p, lower))
    de_matches = sum(1 for p in GERMAN_MARKERS if re.search(p, lower))

    scores = [
        ("fr", fr_matches),
        ("en", en_matches),
        ("es", es_matches),
        ("de", de_matches),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)

    if scores[0][1] >= 1 and scores[0][1] > scores[1][1]:
        return scores[0][0]

    if user_telegram_lang:
        code = user_telegram_lang.lower().split("-")[0].split("_")[0]
        if code in SUPPORTED_LANGUAGES:
            return code

    return DEFAULT_LANGUAGE


def get_user_language(user_id: int, fallback: str = DEFAULT_LANGUAGE) -> str:
    """Get currently active language for a specific user."""
    return _user_languages.get(user_id, fallback)


def set_user_language(user_id: int, lang: str) -> None:
    """Explicitly set user's preferred language."""
    code = (lang or "").lower().strip()
    if code:
        _user_languages[user_id] = code


def detect_and_set_language(user_id: int, text: str, user_telegram_lang: Optional[str] = None) -> str:
    """Detect language from message and update user's session language preference."""
    lang = detect_language(text, user_telegram_lang)
    _user_languages[user_id] = lang
    return lang


def t(key: str, lang: Optional[str] = None, user_id: Optional[int] = None, **kwargs) -> str:
    """
    Retrieve translated string for the given key and language.
    Checks:
      1. Pre-compiled TRANSLATIONS dictionary
      2. Dynamically loaded locales/{lang}.json
      3. English fallback
      4. Key itself
    Substitutes format arguments safely.
    """
    if not lang:
        if user_id:
            lang = get_user_language(user_id)
        else:
            lang = DEFAULT_LANGUAGE

    lang = lang.lower().strip()

    # 1. Check in-memory pre-compiled dictionary
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang)

    # 2. Check loaded locale file for this language
    if not text:
        loc = load_locale_file(lang)
        text = loc.get(key)

    # 3. Fallback to English
    if not text:
        text = entry.get("en") or load_locale_file("en").get(key) or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
