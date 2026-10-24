"""
quota_manager.py - Intelligent AI Model Quota & Usage Manager for Antigravity Bot
Tracks per-model token usage, requests, rate limits, and quota cooldowns.
Provides an autonomous model routing engine ("auto") that preserves premium models (Argon, Claude)
for complex programming/reasoning tasks and routes everyday queries to fast lightweight models (Flash).
Fully internationalized (English default, automatic French localization).
"""

import os
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

# Rolling quota cycle length in seconds (Google Antigravity rolling window: 5 hours)
ROLLING_CYCLE_SECONDS = 5 * 3600


class QuotaManager:
    """
    Manages AI model usage metrics, cooldown states, and rolling reset cycles.
    Persists data in model_quotas.json.
    """

    def __init__(self, filepath: Path = QUOTA_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.filepath.exists():
            try:
                content = self.filepath.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.error(f"Error loading {self.filepath}: {e}")
        return {
            "models": {},
            "last_reset_day": self._today_str(),
            "rolling_cycle_start": time.time(),
        }

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

    def _check_rollover(self):
        """Reset daily counters when UTC day rolls over and manage 5-hour rolling cycle."""
        now = time.time()
        today = self._today_str()
        changed = False

        if self.data.get("last_reset_day") != today:
            self.data["last_reset_day"] = today
            for m in self.data.get("models", {}).values():
                m["requests_today"] = 0
                m["tokens_today"] = 0
                m["input_tokens_today"] = 0
                m["output_tokens_today"] = 0
                m["thinking_tokens_today"] = 0
            changed = True

        cycle_start = self.data.get("rolling_cycle_start", 0)
        if (now - cycle_start) >= ROLLING_CYCLE_SECONDS or cycle_start == 0:
            self.data["rolling_cycle_start"] = now
            changed = True

        if changed:
            self._save()

    def get_rolling_cycle_remaining(self) -> Tuple[int, int]:
        """Returns (hours, minutes) until the next 5-hour rolling quota reset."""
        self._check_rollover()
        cycle_start = self.data.get("rolling_cycle_start", time.time())
        elapsed = time.time() - cycle_start
        remaining = max(0, int(ROLLING_CYCLE_SECONDS - elapsed))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return hours, minutes

    def _get_model_record(self, model: str) -> Dict[str, Any]:
        self._check_rollover()
        models = self.data.setdefault("models", {})
        if model not in models:
            models[model] = {
                "requests_total": 0,
                "requests_today": 0,
                "tokens_total": 0,
                "tokens_today": 0,
                "input_tokens_today": 0,
                "output_tokens_today": 0,
                "thinking_tokens_today": 0,
                "last_used": None,
                "quota_exhausted_until": 0,
                "consecutive_rate_limits": 0,
                "last_error": "",
            }
        return models[model]

    def record_usage(
        self,
        model: str,
        total_tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
    ):
        """Record successful request and tokens consumed for a model, clearing cooldowns."""
        if not model:
            return
        rec = self._get_model_record(model)
        rec["requests_total"] += 1
        rec["requests_today"] += 1
        rec["tokens_total"] += max(0, total_tokens)
        rec["tokens_today"] += max(0, total_tokens)
        rec["input_tokens_today"] = rec.get("input_tokens_today", 0) + max(0, input_tokens)
        rec["output_tokens_today"] = rec.get("output_tokens_today", 0) + max(0, output_tokens)
        rec["thinking_tokens_today"] = rec.get("thinking_tokens_today", 0) + max(0, thinking_tokens)
        rec["last_used"] = time.time()
        # Verified success on live turn: immediately clear any stale cooldown
        rec["quota_exhausted_until"] = 0
        rec["consecutive_rate_limits"] = 0
        rec["last_error"] = ""
        self._save()

    def record_quota_error(self, model: str, error_msg: str, base_cooldown: int = 120):
        """
        Mark a model as temporarily rate-limited with realistic, progressive backoff.
        Default: 120s (2 minutes), scaling to 300s, max 600s. Never locks out for 40m!
        """
        if not model:
            return
        rec = self._get_model_record(model)
        fails = rec.get("consecutive_rate_limits", 0) + 1
        rec["consecutive_rate_limits"] = fails
        cooldown_sec = min(600, base_cooldown * fails)
        rec["quota_exhausted_until"] = time.time() + cooldown_sec
        rec["last_error"] = str(error_msg)[:300]
        logger.warning(
            f"Quota rate-limit for '{model}' (attempt #{fails}). Cooldown: {cooldown_sec}s."
        )
        self._save()

    def reset_cooldowns(self, model: Optional[str] = None) -> int:
        """Force reset quota cooldown locks. Returns number of unblocked models."""
        models = self.data.get("models", {})
        count = 0
        if model:
            if model in models:
                models[model]["quota_exhausted_until"] = 0
                models[model]["consecutive_rate_limits"] = 0
                count = 1
        else:
            for rec in models.values():
                if rec.get("quota_exhausted_until", 0) > 0:
                    rec["quota_exhausted_until"] = 0
                    rec["consecutive_rate_limits"] = 0
                    count += 1
        self._save()
        logger.info(f"Reset quota cooldowns: {count} model(s) unblocked.")
        return count

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
        self._check_rollover()
        prompt_lower = prompt.lower()
        is_complex = len(prompt) > 400 or any(kw in prompt_lower for kw in COMPLEX_TASK_KEYWORDS)

        # 1. Complex Task: Try to assign a top-tier reasoning model
        if is_complex:
            for candidate in ["gemini-4-argon-medium", "gemini-4-argon-high"]:
                if candidate in available_model_ids:
                    limited, remaining = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Tâche complexe ➔ {candidate} (Raisonnement maximal)"

            for candidate in ["claude-sonnet-5-5-medium", "claude-sonnet-5-5-high"]:
                if candidate in available_model_ids:
                    limited, remaining = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Tâche technique ➔ {candidate} (Expertise Code & Synthèse)"

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

        fallback = available_model_ids[0] if available_model_ids else "gemini-3.8-flash-medium"
        return fallback, f"Mode résilient ➔ {fallback}"

    def format_usage_dashboard(self, user_lang: str = "en") -> str:
        """Generate a complete, beautiful HTML dashboard of model quotas and usage."""
        self._check_rollover()
        models = self.data.get("models", {})
        cycle_h, cycle_m = self.get_rolling_cycle_remaining()

        if user_lang == "fr":
            title = "📊 <b>Tableau de Bord — Quotas &amp; Utilisation des Modèles IA</b>\n"
            date_line = f"📅 <b>Date :</b> <code>{self._today_str()} (UTC)</code>"
            cycle_line = f"⏳ <b>Cycle glissant (5h) :</b> Prochaine recharge dans <b>~{cycle_h}h {cycle_m:02d}m</b>\n"
            sec_header = "<b>Modèles Principaux :</b>\n"
            req_label = "req"
            today_label = "Aujourd'hui"
            tot_label = "Total cumulé"
            avail_label = "🟢 <b>Disponible ✅</b>"
            exhausted_label = "⛔ <b>Cooldown Quota</b>"
            tip_text = (
                "💡 <i>Astuce : En choisissant <code>/model ➔ 🤖 Auto</code>, l'agent utilise "
                "automatiquement Flash pour les messages légers afin de préserver votre quota "
                "d'Argon et Claude pour les gros devoirs et codes complexes !</i>\n\n"
                "🔄 <i>Si vos tokens ont été rechargés, cliquez sur 'Réinitialiser les Verrous' ci-dessous.</i>"
            )
        else:
            title = "📊 <b>AI Models Usage &amp; Quota Dashboard</b>\n"
            date_line = f"📅 <b>Date:</b> <code>{self._today_str()} (UTC)</code>"
            cycle_line = f"⏳ <b>Rolling 5h Cycle:</b> Next quota refresh in <b>~{cycle_h}h {cycle_m:02d}m</b>\n"
            sec_header = "<b>Primary Models:</b>\n"
            req_label = "req"
            today_label = "Today"
            tot_label = "All-time"
            avail_label = "🟢 <b>Available ✅</b>"
            exhausted_label = "⛔ <b>Quota Cooldown</b>"
            tip_text = (
                "💡 <i>Tip: With <code>/model ➔ 🤖 Auto</code>, the agent uses fast Flash "
                "for lightweight questions to preserve Argon & Claude quotas for heavy coding and reasoning!</i>\n\n"
                "🔄 <i>If your Google tokens were replenished, click 'Reset Cooldown Locks' below.</i>"
            )

        lines = [title, date_line, cycle_line, sec_header]

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
                mins = max(1, (remaining + 59) // 60)
                st_text = f"{exhausted_label} (Retry in ~{mins}m)"
            else:
                st_text = avail_label

            tok_str = f"{tok_today:,}" if tok_today > 0 else "0"
            lines.append(f"• <b>{mod_label}</b> (<code>{mod_id}</code>)")
            lines.append(f"  └ État : {st_text}")
            lines.append(f"  └ {today_label} : <code>{req_today}</code> {req_label} | <code>{tok_str}</code> tokens")
            lines.append(f"  └ {tot_label} : <code>{req_tot}</code> {req_label} | <code>{tok_tot:,}</code> tokens\n")

        other_models = [m for m in models.keys() if m not in seen_models]
        if other_models:
            lines.append("<b>" + ("Autres Modèles :" if user_lang == "fr" else "Other Models:") + "</b>")
            for mod_id in other_models:
                rec = models[mod_id]
                limited, remaining = self.is_rate_limited(mod_id)
                st = f"⛔ (~{(remaining + 59) // 60}m)" if limited else "🟢 OK"
                lines.append(
                    f"• <code>{mod_id}</code> : {st} | {rec.get('requests_today', 0)} req "
                    f"({rec.get('tokens_today', 0):,} tok)"
                )
            lines.append("")

        lines.append(tip_text)
        return "\n".join(lines)

    def format_quota_dashboard(self, user_lang: str = "en") -> str:
        """Backward-compatible alias for format_usage_dashboard."""
        return self.format_usage_dashboard(user_lang=user_lang)


quota_mgr = QuotaManager()
