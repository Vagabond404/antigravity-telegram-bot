"""
quota_manager.py - Intelligent AI Model Quota & Usage Manager for Antigravity Bot
Tracks per-model and per-family token usage, requests, rate limits, and quota cooldowns.
Provides an autonomous model routing engine ("auto") that preserves premium models (Argon, Claude)
for complex tasks, enforces Google account tier constraints (Free vs Pro vs Ultra),
and delivers accurate real-time token usage gauges with countdowns to reset.
Fully internationalized (English default, dynamic multi-language localization).
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from config import (
    BASE_DIR,
    get_model_family,
    ACCOUNT_TIER_FREE,
    ACCOUNT_TIER_PRO,
    ACCOUNT_TIER_ULTRA,
    ACCOUNT_TIER_AUTO,
)

logger = logging.getLogger("quota_manager")

QUOTA_FILE = BASE_DIR / "model_quotas.json"

# Models considered "premium" with scarce quotas to be preserved
PREMIUM_MODELS = [
    "gemini-4-argon-medium",
    "gemini-4-argon-high",
    "gemini-4-argon-low",
    "claude-sonnet-5-5-medium",
    "claude-sonnet-5-5-high",
    "claude-sonnet-5-5-low",
    "claude-opus-5-5-medium",
    "claude-opus-5-5-high",
    "claude-opus-5-5-low",
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
    "docker", "systemd", "architecture", "algorithme", "algorithm", "math",
    "équation", "equation", "calcul", "calculate", "théorème", "theorem",
    "démontre", "solve", "analyse", "analyze", "optimise", "optimize",
    "performance", "sql", "database", "api", "json", "git", "review",
]

# Rolling window cycle length in seconds (Google Antigravity rolling window: 5 hours)
ROLLING_CYCLE_SECONDS = 5 * 3600

# Estimated rolling token budgets per family by account tier
TIER_FAMILY_BUDGETS = {
    ACCOUNT_TIER_FREE: {
        "gemini": 1_000_000,
        "argon": 0,           # Argon is not supported on standard Free tier
        "claude": 0,          # Claude is not supported or trial-only on Free tier
        "other": 500_000,
    },
    ACCOUNT_TIER_PRO: {
        "gemini": 3_000_000,
        "argon": 400_000,
        "claude": 250_000,
        "other": 1_000_000,
    },
    ACCOUNT_TIER_ULTRA: {
        "gemini": 10_000_000,
        "argon": 1_500_000,
        "claude": 1_000_000,
        "other": 5_000_000,
    },
}


def parse_cooldown_from_error(error_msg: str) -> Optional[int]:
    """
    Intelligently parse wait / cooldown duration in seconds from Antigravity / API error messages.
    Supports formats like:
      - 'reset in 4 hours 12 minutes'
      - 'reset in 4h 12m' / '4h' / '30m'
      - 'wait 3 hours'
      - 'try again in 120s' / 'retry after 60 seconds'
      - 'capacity will reset in 4 hours'
      - 'veuillez patienter 4h 12m'
    """
    if not error_msg:
        return None

    text = str(error_msg).lower()
    total_seconds = 0
    matched = False

    # 1. Match hours (e.g., "4 hours", "4h", "4 heures", "4 hrs")
    h_match = re.search(r"(\d+)\s*(?:hours?|heures?|hrs?|h\b)", text)
    if h_match:
        total_seconds += int(h_match.group(1)) * 3600
        matched = True

    # 2. Match minutes (e.g., "15 minutes", "15m", "15 mins")
    m_match = re.search(r"(\d+)\s*(?:minutes?|mins?|m\b)", text)
    if m_match:
        total_seconds += int(m_match.group(1)) * 60
        matched = True

    # 3. Match seconds (e.g., "30 seconds", "30s", "30 secs")
    s_match = re.search(r"(\d+)\s*(?:seconds?|secs?|s\b)", text)
    if s_match and not h_match and not m_match:
        total_seconds += int(s_match.group(1))
        matched = True

    if matched and total_seconds > 0:
        return total_seconds

    return None


def render_gauge(used: int, total: int, width: int = 10) -> str:
    """Render a visual ASCII progress bar gauge like [██████░░░░] 60%."""
    if total <= 0:
        pct = 100 if used > 0 else 0
    else:
        pct = min(100, int((used / total) * 100))

    filled = int(round((pct / 100.0) * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"


class QuotaManager:
    """
    Manages Antigravity AI model usage metrics, cooldown states, and rolling reset cycles.
    Tracks distinct quotas for Gemini (Flash), Argon, and Claude model families.
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
            "families": {
                "gemini": {"tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": time.time()},
                "argon": {"tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": time.time()},
                "claude": {"tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": time.time()},
                "other": {"tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": time.time()},
            },
            "last_reset_day": self._today_str(),
            "detected_tier": ACCOUNT_TIER_AUTO,
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
        """Reset daily counters when UTC day rolls over and manage rolling cycles per family."""
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

        families = self.data.setdefault("families", {})
        for fam_name in ("gemini", "argon", "claude", "other"):
            frec = families.setdefault(fam_name, {
                "tokens_cycle": 0,
                "requests_cycle": 0,
                "exhausted_until": 0,
                "cycle_start": now,
            })
            c_start = frec.get("cycle_start", 0)
            # If 5 hours elapsed since the cycle started, roll over token cycle counter
            if (now - c_start) >= ROLLING_CYCLE_SECONDS or c_start == 0:
                frec["tokens_cycle"] = 0
                frec["requests_cycle"] = 0
                frec["cycle_start"] = now
                changed = True

            # If cooldown has expired, clear it
            if frec.get("exhausted_until", 0) > 0 and now >= frec["exhausted_until"]:
                frec["exhausted_until"] = 0
                changed = True

        # Check model cooldowns expiration
        for m in self.data.get("models", {}).values():
            if m.get("quota_exhausted_until", 0) > 0 and now >= m["quota_exhausted_until"]:
                m["quota_exhausted_until"] = 0
                m["consecutive_rate_limits"] = 0
                changed = True

        if changed:
            self._save()

    def get_family_cycle_remaining(self, family: str) -> Tuple[int, int]:
        """Returns (hours, minutes) until the 5-hour rolling cycle refreshes for a given family."""
        self._check_rollover()
        frec = self.data.get("families", {}).get(family, {})
        # If there is an active explicit cooldown, use that remaining time!
        ex_until = frec.get("exhausted_until", 0)
        now = time.time()
        if ex_until > now:
            rem = int(ex_until - now)
            return rem // 3600, (rem % 3600) // 60

        c_start = frec.get("cycle_start", now)
        elapsed = now - c_start
        remaining = max(0, int(ROLLING_CYCLE_SECONDS - elapsed))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return hours, minutes

    def _get_model_record(self, model: str) -> Dict[str, Any]:
        self._check_rollover()
        models = self.data.setdefault("models", {})
        if model not in models:
            models[model] = {
                "family": get_model_family(model),
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
        self._check_rollover()
        rec = self._get_model_record(model)
        fam = get_model_family(model)
        tok = max(0, total_tokens)

        rec["requests_total"] += 1
        rec["requests_today"] += 1
        rec["tokens_total"] += tok
        rec["tokens_today"] += tok
        rec["input_tokens_today"] = rec.get("input_tokens_today", 0) + max(0, input_tokens)
        rec["output_tokens_today"] = rec.get("output_tokens_today", 0) + max(0, output_tokens)
        rec["thinking_tokens_today"] = rec.get("thinking_tokens_today", 0) + max(0, thinking_tokens)
        rec["last_used"] = time.time()
        # Verified success on live turn: immediately clear any stale cooldown
        rec["quota_exhausted_until"] = 0
        rec["consecutive_rate_limits"] = 0
        rec["last_error"] = ""

        frec = self.data.setdefault("families", {}).setdefault(fam, {
            "tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": time.time()
        })
        frec["tokens_cycle"] = frec.get("tokens_cycle", 0) + tok
        frec["requests_cycle"] = frec.get("requests_cycle", 0) + 1
        frec["exhausted_until"] = 0

        self._save()

    def record_quota_error(self, model: str, error_msg: str, default_cooldown: int = 180):
        """
        Mark a model and its family as temporarily quota-limited with parsed or progressive cooldown.
        Extracts exact duration from error if present (e.g. 'reset in 4 hours 12 minutes').
        """
        if not model:
            return
        self._check_rollover()
        rec = self._get_model_record(model)
        fam = get_model_family(model)

        parsed_secs = parse_cooldown_from_error(error_msg)
        now = time.time()

        if parsed_secs and parsed_secs > 0:
            cooldown_sec = parsed_secs
            logger.info(f"Parsed exact quota wait time from error for '{model}': {cooldown_sec}s")
        else:
            fails = rec.get("consecutive_rate_limits", 0) + 1
            rec["consecutive_rate_limits"] = fails
            cooldown_sec = min(3600, default_cooldown * fails)

        until = now + cooldown_sec
        rec["quota_exhausted_until"] = until
        rec["last_error"] = str(error_msg)[:300]

        # Also set the family-wide cooldown so other models in the same exhausted bucket aren't futilely hammered
        frec = self.data.setdefault("families", {}).setdefault(fam, {
            "tokens_cycle": 0, "requests_cycle": 0, "exhausted_until": 0, "cycle_start": now
        })
        frec["exhausted_until"] = until

        logger.warning(
            f"Quota rate-limit recorded for model '{model}' (family: {fam}). Cooldown: {cooldown_sec}s."
        )
        self._save()

    def reset_cooldowns(self, model_or_family: Optional[str] = None) -> int:
        """Force reset quota cooldown locks. Returns number of unblocked models."""
        self._check_rollover()
        models = self.data.get("models", {})
        families = self.data.get("families", {})
        count = 0

        if model_or_family:
            target = model_or_family.lower()
            if target in families:
                families[target]["exhausted_until"] = 0
                for rec in models.values():
                    if rec.get("family") == target and rec.get("quota_exhausted_until", 0) > 0:
                        rec["quota_exhausted_until"] = 0
                        rec["consecutive_rate_limits"] = 0
                        count += 1
            elif target in models:
                if models[target].get("quota_exhausted_until", 0) > 0:
                    models[target]["quota_exhausted_until"] = 0
                    models[target]["consecutive_rate_limits"] = 0
                    count = 1
        else:
            for frec in families.values():
                frec["exhausted_until"] = 0
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
        self._check_rollover()
        rec = self._get_model_record(model)
        until = rec.get("quota_exhausted_until", 0)
        now = time.time()
        if until > now:
            return True, int(until - now)

        # Also check family-wide exhaustion
        fam = get_model_family(model)
        frec = self.data.get("families", {}).get(fam, {})
        fam_until = frec.get("exhausted_until", 0)
        if fam_until > now:
            return True, int(fam_until - now)

        return False, 0

    def select_optimal_model(
        self,
        prompt: str,
        available_model_ids: List[str],
        account_tier: str = ACCOUNT_TIER_AUTO,
    ) -> Tuple[str, str]:
        """
        Intelligently choose the best model for this specific prompt:
        - If Free account tier -> Strictly routes to Gemini Flash (prevents instant quota error on Argon/Claude).
        - If Pro/Ultra and task is complex (code, math, architecture) -> Uses Argon / Claude if available.
        - If prompt is simple / conversational -> Preserves precious quotas, routes to Fast Gemini Flash.
        - If preferred model is in quota cooldown -> Falls back automatically to next available model.
        Returns (chosen_model, reasoning_label).
        """
        self._check_rollover()
        prompt_lower = prompt.lower()
        is_complex = len(prompt) > 400 or any(kw in prompt_lower for kw in COMPLEX_TASK_KEYWORDS)

        # Tier Resolution: If Free tier is explicitly configured or detected
        is_free_tier = (account_tier == ACCOUNT_TIER_FREE)

        # 1. Free Tier: Route exclusively to Gemini Flash models
        if is_free_tier:
            for candidate in FAST_MODELS:
                if candidate in available_model_ids:
                    limited, _ = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Free Plan ➔ {candidate} (Flash Generous Quota)"
            # Fallback to any non-limited model
            for m in available_model_ids:
                if "argon" not in m and "claude" not in m:
                    return m, f"Free Plan ➔ {m}"

        # 2. Pro / Ultra Plan - Complex Task: Assign Argon or Claude
        if is_complex:
            # First try Argon (Top Google reasoning)
            for candidate in ["gemini-4-argon-medium", "gemini-4-argon-high", "gemini-4-argon-low"]:
                if candidate in available_model_ids:
                    limited, _ = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Complex Task ➔ {candidate} (Deep Reasoning)"

            # Next try Claude (Code & synthesis specialist)
            for candidate in ["claude-sonnet-5-5-medium", "claude-sonnet-5-5-high", "claude-sonnet-5-5-low"]:
                if candidate in available_model_ids:
                    limited, _ = self.is_rate_limited(candidate)
                    if not limited:
                        return candidate, f"Technical Task ➔ {candidate} (Claude Synthesis)"

            # If premium models in cooldown, fall back cleanly to Flash
            for candidate in FAST_MODELS:
                if candidate in available_model_ids:
                    return candidate, f"Heavy Models on Cooldown ➔ {candidate} (Resilient Fallback)"

        # 3. Standard / Everyday Query: Always use Flash to preserve Argon & Claude quotas!
        for candidate in ["gemini-3.8-flash-medium", "gemini-3.8-flash-high", "gemini-3.8-flash-low"]:
            if candidate in available_model_ids:
                limited, _ = self.is_rate_limited(candidate)
                if not limited:
                    return candidate, f"Standard Query ➔ {candidate} (Fast & Quota Preserved)"

        # 4. Default fallback: Pick any model that is NOT rate-limited
        for m in available_model_ids:
            limited, _ = self.is_rate_limited(m)
            if not limited:
                return m, f"Auto Route ➔ {m}"

        fallback = available_model_ids[0] if available_model_ids else "gemini-3.8-flash-medium"
        return fallback, f"Resilient Default ➔ {fallback}"

    def format_usage_dashboard(
        self,
        user_lang: str = "en",
        account_tier: str = ACCOUNT_TIER_AUTO,
    ) -> str:
        """
        Generate a complete, beautiful HTML dashboard of model quotas and token usage gauges
        for the 3 distinct Antigravity token buckets: Gemini, Argon, and Claude.
        """
        self._check_rollover()
        families = self.data.get("families", {})
        models = self.data.get("models", {})

        tier_key = account_tier if account_tier in TIER_FAMILY_BUDGETS else ACCOUNT_TIER_PRO
        budgets = TIER_FAMILY_BUDGETS[tier_key]

        is_fr = (user_lang == "fr")

        # Titles and Section Labels
        if is_fr:
            title = "📊 <b>Tableau de Bord — Quotas &amp; Utilisation des Tokens IA</b>\n"
            plan_label = f"🏷️ <b>Forfait Google :</b> <code>{account_tier.upper()}</code>"
            date_line = f"📅 <b>Date :</b> <code>{self._today_str()} (UTC)</code>\n"
            gauges_header = "<b>Jauges d'Utilisation des Tokens Antigravity :</b>\n"
            avail_text = "🟢 <b>Disponible ✅</b>"
            exhausted_text = "⛔ <b>Cooldown / Épuisé</b>"
            pro_required_text = "🔒 <b>Réservé au Forfait Pro / Ultra</b>"
            sec_models = "\n<b>Détails par Modèle :</b>"
            tip_text = (
                "💡 <i>Astuce : En choisissant <code>/model ➔ 🤖 Auto</code>, l'agent utilise "
                "automatiquement Flash pour les messages standards afin de préserver votre quota "
                "d'Argon et Claude pour les gros devoirs et codes complexes !</i>\n\n"
                "🔄 <i>Si vos tokens ont été rechargés par Google, cliquez sur 'Réinitialiser les Verrous' ci-dessous.</i>"
            )
        else:
            title = "📊 <b>AI Models &amp; Token Usage Dashboard</b>\n"
            plan_label = f"🏷️ <b>Google Plan:</b> <code>{account_tier.upper()}</code>"
            date_line = f"📅 <b>Date:</b> <code>{self._today_str()} (UTC)</code>\n"
            gauges_header = "<b>Antigravity Token Usage Gauges:</b>\n"
            avail_text = "🟢 <b>Available ✅</b>"
            exhausted_text = "⛔ <b>Cooldown / Exhausted</b>"
            pro_required_text = "🔒 <b>Pro / Ultra Plan Required</b>"
            sec_models = "\n<b>Per-Model Breakdown:</b>"
            tip_text = (
                "💡 <i>Tip: With <code>/model ➔ 🤖 Auto</code>, the agent automatically routes "
                "everyday questions to fast Flash to preserve Argon & Claude quotas for heavy coding and reasoning!</i>\n\n"
                "🔄 <i>If your Google tokens were replenished, click 'Reset Cooldown Locks' below.</i>"
            )

        lines = [title, plan_label, date_line, gauges_header]

        family_configs = [
            ("gemini", "⚡ Gemini (Flash)", "gemini-3.8-flash-medium"),
            ("argon", "🧠 Argon (Gemini 4 Argon)", "gemini-4-argon-medium"),
            ("claude", "📜 Claude (Sonnet / Opus)", "claude-sonnet-5-5-medium"),
        ]

        now = time.time()

        for fam_key, fam_title, rep_model in family_configs:
            frec = families.get(fam_key, {})
            used_tok = frec.get("tokens_cycle", 0)
            budget = budgets.get(fam_key, 0)
            c_h, c_m = self.get_family_cycle_remaining(fam_key)

            # Check if rate limited
            ex_until = frec.get("exhausted_until", 0)
            is_limited = ex_until > now

            gauge_bar = render_gauge(used_tok, budget if budget > 0 else 1)

            if account_tier == ACCOUNT_TIER_FREE and budget == 0:
                status_str = pro_required_text
                gauge_str = "[░░░░░░░░░░] N/A"
            elif is_limited:
                rem_sec = int(ex_until - now)
                m_left = max(1, (rem_sec + 59) // 60)
                h_left = m_left // 60
                m_sub = m_left % 60
                time_str = f"{h_left}h {m_sub:02d}m" if h_left > 0 else f"{m_left}m"
                reset_utc = datetime.fromtimestamp(ex_until, timezone.utc).strftime("%H:%M UTC")
                status_str = f"{exhausted_text} (Recharge dans ~{time_str} à {reset_utc})" if is_fr else f"{exhausted_text} (Resets in ~{time_str} at {reset_utc})"
                gauge_str = f"{gauge_bar} (<code>{used_tok:,}</code> tok)"
            else:
                status_str = f"{avail_text} (Cycle 5h : ~{c_h}h {c_m:02d}m)" if is_fr else f"{avail_text} (5h Cycle: ~{c_h}h {c_m:02d}m)"
                budget_str = f"{budget:,}" if budget > 0 else "∞"
                gauge_str = f"{gauge_bar} (<code>{used_tok:,} / {budget_str}</code> tok)"

            lines.append(f"• <b>{fam_title}</b>")
            lines.append(f"  └ {gauge_str}")
            lines.append(f"  └ État : {status_str}" if is_fr else f"  └ Status: {status_str}\n")

        lines.append(sec_models)

        known_display_order = [
            ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)"),
            ("gemini-4-argon-medium", "Gemini 4 Argon (Medium)"),
            ("claude-sonnet-5-5-medium", "Claude Sonnet 5.5 (Medium)"),
            ("claude-opus-5-5-medium", "Claude Opus 5.5 (Medium)"),
        ]

        seen_models = set()
        for mod_id, mod_label in known_display_order:
            seen_models.add(mod_id)
            rec = models.get(mod_id, {})
            req_today = rec.get("requests_today", 0)
            tok_today = rec.get("tokens_today", 0)
            tok_str = f"{tok_today:,}" if tok_today > 0 else "0"
            limited, remaining = self.is_rate_limited(mod_id)

            if limited:
                mins = max(1, (remaining + 59) // 60)
                st = f"⛔ Cooldown (~{mins}m)"
            else:
                st = "🟢 OK"

            lines.append(
                f"• <b>{mod_label}</b>: {st} | <code>{req_today}</code> req | <code>{tok_str}</code> tok"
            )

        lines.append("")
        lines.append(tip_text)
        return "\n".join(lines)

    def format_quota_dashboard(self, user_lang: str = "en", account_tier: str = ACCOUNT_TIER_AUTO) -> str:
        """Backward-compatible alias for format_usage_dashboard."""
        return self.format_usage_dashboard(user_lang=user_lang, account_tier=account_tier)


quota_mgr = QuotaManager()
