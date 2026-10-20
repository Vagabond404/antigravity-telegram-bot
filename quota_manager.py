"""
quota_manager.py - Intelligent Model Quota Tracker & Dynamic Model Selector for Antigravity Bot
Tracks per-model token usage, requests, rate limits, and quota cooldowns.
Provides an autonomous model routing engine ("auto") that preserves premium models (Argon, Claude)
for complex programming/reasoning tasks and routes everyday queries to fast lightweight models (Flash).
"""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from config import BASE_DIR

logger = logging.getLogger("quota_manager")

QUOTA_FILE = BASE_DIR / "model_quotas.json"

# Models considered "premium" with strict or scarce quotas to be preserved
PREMIUM_MODELS = [
    "gemini-4-argon-medium",
    "gemini-4-argon-high",
    "gemini-4-argon-low",
    "claude-sonnet-5-5-medium",
    "claude-sonnet-5-5-high",
    "claude-opus-5-5-medium",
    "claude-opus-5-5-high",
]

# Fast lightweight models with generous or high-throughput limits
FAST_MODELS = [
    "gemini-3.8-flash-medium",
    "gemini-3.8-flash-high",
    "gemini-3.8-flash-low",
]

# Keywords indicating complex reasoning, coding, math, or architectural tasks
COMPLEX_TASK_KEYWORDS = [
    "code", "script", "python", "bash", "linux", "bug", "erreur", "error",
    "debug", "fonction", "function", "class", "def ", "import ", "refactor",
    "docker", "systemd", "architecture", "algorithme", "math", "équation",
    "equation", "calcul", "théorème", "démontre", "solve", "analyse",
    "optimise", "performance", "sql", "database", "api", "json", "git"
]


class QuotaManager:
    def __init__(self, filepath: Path = QUOTA_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.filepath.exists():
            try:
                content = self.filepath.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception as e:
                logger.error(f"Error loading {self.filepath}: {e}")
        return {"models": {}, "last_reset_day": self._today_str()}

    def _save(self) -> bool:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.filepath.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            logger.error(f"Error saving {self.filepath}: {e}")
            return False

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_day_rollover(self):
        today = self._today_str()
        if self.data.get("last_reset_day") != today:
            self.data["last_reset_day"] = today
            for m in self.data.get("models", {}).values():
                m["requests_today"] = 0
                m["tokens_today"] = 0
            self._save()

    def _get_model_record(self, model: str) -> Dict[str, Any]:
        self._check_day_rollover()
        models = self.data.setdefault("models", {})
        if model not in models:
            models[model] = {
                "requests_total": 0,
                "requests_today": 0,
                "tokens_total": 0,
                "tokens_today": 0,
                "last_used": None,
                "quota_exhausted_until": 0,
                "last_error": "",
            }
        return models[model]

    def record_usage(self, model: str, tokens: int = 0):
        """Record successful request and tokens consumed for a model."""
        if not model:
            return
        rec = self._get_model_record(model)
        rec["requests_total"] += 1
        rec["requests_today"] += 1
        rec["tokens_total"] += max(0, tokens)
        rec["tokens_today"] += max(0, tokens)
        rec["last_used"] = time.time()
        # Clear cooldown on verified success
        if rec.get("quota_exhausted_until", 0) <= time.time():
            rec["quota_exhausted_until"] = 0
        self._save()

    def record_quota_error(self, model: str, error_msg: str, cooldown_seconds: int = 2400):
        """Mark a model as temporarily rate-limited (default cooldown: 40 minutes)."""
        if not model:
            return
        rec = self._get_model_record(model)
        rec["quota_exhausted_until"] = time.time() + cooldown_seconds
        rec["last_error"] = str(error_msg)[:300]
        logger.warning(
            f"Quota rate-limit recorded for '{model}'. Cooldown set until +{cooldown_seconds}s."
        )
        self._save()

    def is_rate_limited(self, model: str) -> Tuple[bool, int]:
        """Returns (is_limited, remaining_cooldown_seconds)."""
        if not model:
            return False, 0
        rec = self._get_model_record(model)
        until = rec.get("quota_exhausted_until", 0)
        now = time.time()
        if until > now:
            return True, int(until - now)
        return False, 0

    def select_optimal_model(
        self,
        prompt: str,
        available_model_ids: List[str],
    ) -> Tuple[str, str]:
        """
        Intelligently choose the best model for this specific prompt:
        - If prompt is complex (code, math, architecture, deep debugging) -> Uses Argon / Claude
        - If prompt is simple / conversational -> Preserves precious quotas, routes to Fast Gemini Flash
        - If preferred model is in quota cooldown -> Falls back automatically
        Returns (chosen_model, reasoning_label).
        """
        self._check_day_rollover()
        prompt_lower = prompt.lower()
        is_complex = len(prompt) > 400 or any(kw in prompt_lower for kw in COMPLEX_TASK_KEYWORDS)

        # 1. Complex Task: Try to assign a top-tier reasoning model
        if is_complex:
            # Try Argon first
            for candidate in ["gemini-4-argon-medium", "gemini-4-argon-high"]:
                if candidate in available_model_ids:
                    limited, remaining = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Tâche complexe/technique ➔ {candidate} (Raisonnement maximal)"

            # Try Claude Sonnet next
            for candidate in ["claude-sonnet-5-5-medium", "claude-sonnet-5-5-high"]:
                if candidate in available_model_ids:
                    limited, remaining = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Tâche technique ➔ {candidate} (Expertise Code & Synthèse)"

            # Fallback to Flash if premium models are quota-limited
            for candidate in FAST_MODELS:
                if candidate in available_model_ids:
                    return candidate, f"Modèles lourds en cooldown ➔ {candidate} (Repli intelligent)"

        # 2. Standard / Lightweight Task: Use Flash to preserve precious quotas
        for candidate in ["gemini-3.8-flash-medium", "gemini-3.8-flash-high", "gemini-3.8-flash-low"]:
            if candidate in available_model_ids:
                limited, _ = self.is_rate_limited(candidate)
                if not limited:
                    return candidate, f"Discussion standard ➔ {candidate} (Rapide & Quota préservé)"

        # 3. Default fallback to whatever model is not rate limited
        for m in available_model_ids:
            limited, _ = self.is_rate_limited(m)
            if not limited:
                return m, f"Sélection auto ➔ {m}"

        # If everything is rate limited, return the first available model
        fallback = available_model_ids[0] if available_model_ids else "gemini-3.8-flash-medium"
        return fallback, f"Mode résilient ➔ {fallback}"

    def format_quota_dashboard(self, user_lang: str = "fr") -> str:
        """Generate a complete HTML dashboard of model quotas and usage."""
        self._check_day_rollover()
        models = self.data.get("models", {})

        if user_lang == "fr":
            lines = [
                "📊 <b>Quotas &amp; Utilisation des Modèles IA</b>\n",
                f"📅 <b>Date :</b> <code>{self._today_str()} (UTC)</code>\n",
            ]
        else:
            lines = [
                "📊 <b>AI Models Quota &amp; Usage Dashboard</b>\n",
                f"📅 <b>Date :</b> <code>{self._today_str()} (UTC)</code>\n",
            ]

        # Prioritize known major models
        known_display_order = [
            ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)"),
            ("gemini-4-argon-medium", "Gemini 4 Argon (Medium)"),
            ("claude-sonnet-5-5-medium", "Claude Sonnet 5.5 (Medium)"),
            ("claude-opus-5-5-medium", "Claude Opus 5.5 (Medium)"),
            ("gpt-oss-120b-medium", "GPT-OSS 120B (Medium)"),
        ]

        seen_models = set()
        for mod_id, mod_label in known_display_order:
            seen_models.add(mod_id)
            rec = models.get(mod_id, {})
            req_today = rec.get("requests_today", 0)
            tok_today = rec.get("tokens_today", 0)
            req_tot = rec.get("requests_total", 0)
            tok_tot = rec.get("tokens_total", 0)
            limited, remaining = self.is_rate_limited(mod_id)

            if limited:
                mins = max(1, remaining // 60)
                st_icon = "⛔"
                st_text = f"<b>Quota Épuisé</b> (Disponible dans ~{mins} min)" if user_lang == "fr" else f"<b>Quota Exceeded</b> (Resets in ~{mins}m)"
            else:
                st_icon = "🟢"
                st_text = "<b>Disponible ✅</b>" if user_lang == "fr" else "<b>Available ✅</b>"

            tok_str = f"{tok_today:,}" if tok_today > 0 else "0"
            lines.append(f"{st_icon} <b>{mod_label}</b> (<code>{mod_id}</code>)")
            lines.append(f"  • État : {st_text}")
            lines.append(f"  • Aujourd'hui : <code>{req_today}</code> req | <code>{tok_str}</code> tokens")
            lines.append(f"  • Total cumulé : <code>{req_tot}</code> req | <code>{tok_tot:,}</code> tokens\n")

        # Other models
        other_models = [m for m in models.keys() if m not in seen_models]
        if other_models:
            lines.append("<b>Autres Modèles Utilisés :</b>")
            for mod_id in other_models:
                rec = models[mod_id]
                limited, remaining = self.is_rate_limited(mod_id)
                st = f"⛔ (attente {remaining // 60}m)" if limited else "🟢 Actif"
                lines.append(
                    f"• <code>{mod_id}</code> : {st} | {rec.get('requests_today', 0)} req "
                    f"({rec.get('tokens_today', 0):,} tokens)"
                )
            lines.append("")

        if user_lang == "fr":
            lines.append(
                "💡 <i>Astuce : En choisissant <code>/model ➔ 🤖 Auto</code>, l'agent utilise "
                "automatiquement Flash pour les messages légers afin de préserver votre quota "
                "d'Argon et Claude pour les gros devoirs et codes complexes !</i>"
            )
        else:
            lines.append(
                "💡 <i>Tip: With <code>/model ➔ 🤖 Auto</code>, the agent uses fast Flash "
                "for lightweight questions to preserve Argon & Claude quotas for heavy coding and reasoning!</i>"
            )

        return "\n".join(lines)


quota_mgr = QuotaManager()
