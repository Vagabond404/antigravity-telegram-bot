"""
agent_runner.py - Universal Antigravity CLI Execution Engine (Windows, Linux, macOS)
Fully adapted to the latest Antigravity CLI (`agy`):
- Dynamic model discovery via `agy models` + automatic quota fallback
- All reasoning effort levels (`low`, `medium`, `high`, `xhigh`, `max`, `auto`)
- All execution modes (`auto-approve`, `accept-edits`, `plan`) & `--sandbox`
- Native Multi-Agent & Subagent orchestration (`invoke_subagent`, `define_subagent`, child conversation streams)
- Session persistence via `--conversation <id>` and `--continue`
- Live management of MCP servers (`agy mcp`), Plugins (`agy plugin`), Remote Control (`agy remote-control`), and CLI updates (`agy update`)
- Cross-platform process group management (zero `os.setsid` crashes on Windows)
"""

import asyncio
import os
import sys
import signal
import subprocess
import logging
import json
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any, Tuple

import config
from config import (
    BASE_DIR,
    TEMP_DIR,
    IS_WINDOWS,
    find_agy_binary,
    record_conversation,
)
from memory_manager import get_relevant_context, auto_extract_and_store_facts
from group_manager import group_mgr
from resource_governor import governor

logger = logging.getLogger("agent_runner")

DEFAULT_MODELS_LIST: List[Tuple[str, str]] = [
    ("gemini-4-argon-medium", "Gemini 4 Argon (Medium)"),
    ("gemini-4-argon-high", "Gemini 4 Argon (High)"),
    ("gemini-4-argon-low", "Gemini 4 Argon (Low)"),
    ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)"),
    ("gemini-3.8-flash-high", "Gemini 3.8 Flash (High)"),
    ("gemini-3.8-flash-low", "Gemini 3.8 Flash (Low)"),
    ("claude-sonnet-5-5-medium", "Claude Sonnet 5.5 (Medium)"),
    ("claude-sonnet-5-5-high", "Claude Sonnet 5.5 (High)"),
    ("claude-sonnet-5-5-low", "Claude Sonnet 5.5 (Low)"),
    ("claude-opus-5-5-medium", "Claude Opus 5.5 (Medium)"),
    ("claude-opus-5-5-high", "Claude Opus 5.5 (High)"),
    ("claude-opus-5-5-low", "Claude Opus 5.5 (Low)"),
    ("gpt-oss-120b-medium", "GPT-OSS 120B (Medium)"),
]

_cached_models: List[Tuple[str, str]] = list(DEFAULT_MODELS_LIST)
_models_fetched_once: bool = True

QUOTA_ERROR_KEYWORDS = [
    "quota",
    "resource_exhausted",
    "rate limit",
    "429",
    "exhausted",
    "token limit",
    "credits",
    "out of tokens",
    "quota exceeded",
    "insufficient_quota",
    "overloaded",
]

VALID_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def is_quota_error(error_msg: str) -> bool:
    if not error_msg:
        return False
    lower = error_msg.lower()
    return any(k in lower for k in QUOTA_ERROR_KEYWORDS)


def resolve_effort_flag(model_name: str, requested_effort: str) -> Optional[str]:
    """
    Determine whether to pass --effort to `agy`.
    If requested_effort is 'auto' or empty, let the model use its default effort.
    Otherwise pass the requested effort level ('low', 'medium', 'high', 'xhigh', 'max').
    """
    if not requested_effort or requested_effort == "auto":
        return None
    eff = requested_effort.lower().strip()
    if eff in VALID_EFFORT_LEVELS:
        return eff
    return None


def build_system_prompt(settings: dict) -> str:
    agent_name = settings.get("agent_name", "Antigravity Agent")
    multi_agent = settings.get("multi_agent", True)
    custom_instr = settings.get("custom_instructions", "").strip()
    py_exe = sys.executable
    tg_send_script = str(BASE_DIR / "tg_send.py")
    mem_script = str(BASE_DIR / "mem.py")
    browser_script = str(BASE_DIR / "browser_tool.py")
    cmd_script = str(BASE_DIR / "command_manager.py")

    prompt = f"""[RÔLE & IDENTITÉ DE L'AGENT]
Tu es {agent_name}, un assistant IA personnel autonome propulsé par Google Antigravity CLI et connecté en temps réel à Telegram.
Système hôte : {'Windows' if IS_WINDOWS else 'Linux/Unix'} | Répertoire bot : `{BASE_DIR}`
Skill intégré de maîtrise du bot : `telegram-bot-mastery` (`.agents/skills/telegram-bot-mastery/SKILL.md`).

RÈGLES DE COMMUNICATION & D'EXÉCUTION :
1. ⚡ SUIVI EN DIRECT INTÉGRÉ : Telegram affiche déjà en temps réel ta réflexion, tes outils, tes sous-agents et ton avancement via un message dynamique animé. N'exécute PAS `tg_send` pour dire "Je vais faire..." ou "Analyse en cours...".
2. 📤 ENVOI MULTIMÉDIA DIRECT SUR TELEGRAM (IMAGES, VIDÉOS, AUDIO, DOCUMENTS) :
   Dès que tu génères, télécharges ou prépares un fichier pour l'utilisateur (image, graphique, PDF, vidéo, audio, archive, code), envoie-le directement sur Telegram avec la commande :
   `"{py_exe}" "{tg_send_script}" --file "<chemin_absolu_du_fichier>" --caption "Description"`
   - Pour forcer un type précis : `--photo`, `--video`, `--audio`, `--voice`, ou `--document`.
3. 🧠 MÉMOIRE LONG-TERME PROACTIVE INTER-CONVERSATIONS (Mem0 / SQLite) :
   Tu DOIS conserver la mémoire entre toutes les discussions (même après `/clear` ou redémarrage) :
   - Dès que l'utilisateur partage une **info personnelle** (prénom, métier, appareils, serveurs, OS), une **préférence** (langage, style, habitudes) ou une **règle**, enregistre-la PROACTIVEMENT sans attendre qu'on te le demande :
     `"{py_exe}" "{mem_script}" add "<fait précis>" --category <profile|preferences|rules|infra> --key "<identifiant_court>" --importance 5`
   - Dès que tu travailles sur un **projet** (nouveau projet, architecture, chemin du dossier, stack, avancement, décisions techniques), enregistre ou mets à jour sa mémoire via sa clé unique :
     `"{py_exe}" "{mem_script}" add "<Nom du projet : dossier, stack, état actuel>" --category projet --key "projet_<nom>" --importance 5`
   - Pour rechercher dans toute ta mémoire : `"{py_exe}" "{mem_script}" search "<requête>"`
   - Pour lister tous tes souvenirs : `"{py_exe}" "{mem_script}" list`
4. 🌐 RECHERCHE, NAVIGATION & CAPTURE WEB :
   - Tu peux utiliser tes outils natifs (`search_web`, `read_url_content`, `generate_image`), tes serveurs MCP (`playwright`, `firecrawl`, `context7`, `docker`, etc.) ou l'outil navigateur :
     `"{py_exe}" "{browser_script}" search "<requête>"`
     `"{py_exe}" "{browser_script}" fetch "<url>"`
     `"{py_exe}" "{browser_script}" screenshot "<url>" --send-tg --caption "Capture"`
5. 🕹️ COMMANDES TELEGRAM DYNAMIQUES :
   - Tu peux créer ou supprimer des commandes Telegram (`/nom`) à la demande de l'utilisateur :
     `"{py_exe}" "{cmd_script}" add <nom> "<description>" "<template {{prompt}}>"`
"""
    if multi_agent:
        prompt += """6. 🤝 ORCHESTRATION MULTI-AGENTS & SOUS-AGENTS :
   - Tu disposes des outils natifs `invoke_subagent`, `define_subagent`, `manage_subagents` et `send_message`.
   - Pour les tâches complexes, de recherche multiple ou de développement parallèle, n'hésite pas à définir et lancer des sous-agents spécialisés en parallèle (`self`, `research`, ou des sous-agents sur mesure via `define_subagent`).
"""
    if custom_instr:
        prompt += f"\n[INSTRUCTIONS PERSONNALISÉES DE L'ADMINISTRATEUR]\n{custom_instr}\n"

    return prompt.strip()


def _build_agy_env() -> Dict[str, str]:
    """Build environment variables for `agy` subprocesses across CLI and systemd."""
    env = {
        **os.environ,
        "TERM": "dumb",
        "NO_COLOR": "1",
        "PYTHONUNBUFFERED": "1",
        "HOME": os.environ.get("HOME") or str(Path.home()),
    }
    if not IS_WINDOWS:
        # Ensure `agy` under systemd uses the same file-based token store as interactive SSH sessions
        env.setdefault("SSH_CONNECTION", "1")
        # Force Node.js / agy to resolve IPv4 first to eliminate multi-minute IPv6 timeouts on Linux/Armbian
        env.setdefault("NODE_OPTIONS", "--dns-result-order=ipv4first")
    return env


async def run_agy_subcommand(args: List[str], timeout: float = 15.0) -> Tuple[int, str, str]:
    """Run an `agy` CLI subcommand asynchronously and return (returncode, stdout, stderr)."""
    bin_path = find_agy_binary()
    if not bin_path:
        return 1, "", "Binaire Antigravity CLI (`agy`) introuvable."

    cmd = [bin_path] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BASE_DIR),
            env=_build_agy_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        return 1, "", f"Délai dépassé ({timeout}s) lors de l'exécution de : agy {' '.join(args)}"
    except Exception as e:
        return 1, "", str(e)


async def fetch_available_models(force_refresh: bool = False) -> List[Tuple[str, str]]:
    """
    Query `agy models` to get the live list of supported models.
    Returns a list of (model_id, display_name) tuples.
    """
    global _cached_models, _models_fetched_once
    if _models_fetched_once and not force_refresh and _cached_models:
        return _cached_models

    rc, out, _ = await run_agy_subcommand(["models"], timeout=15.0)
    if rc == 0 and out:
        parsed: List[Tuple[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("fetching"):
                continue
            if "\t" in line:
                parts = line.split("\t", 1)
                mod_id, mod_label = parts[0].strip(), parts[1].strip()
                if mod_id:
                    parsed.append((mod_id, mod_label or mod_id))
            else:
                tokens = line.split(maxsplit=1)
                if len(tokens) == 2 and "-" in tokens[0]:
                    parsed.append((tokens[0].strip(), tokens[1].strip()))
                elif len(tokens) == 1 and "-" in tokens[0]:
                    parsed.append((tokens[0].strip(), tokens[0].strip()))
        if parsed:
            _cached_models = parsed
            _models_fetched_once = True
            return _cached_models

    return _cached_models


def get_cached_models() -> List[Tuple[str, str]]:
    return list(_cached_models)


async def fetch_available_agents() -> List[Dict[str, str]]:
    """Query `agy agents` to list configured CLI agents."""
    rc, out, _ = await run_agy_subcommand(["agents"], timeout=10.0)
    agents: List[Dict[str, str]] = [
        {"name": "", "description": "Agent Principal par défaut (Auto)"},
        {"name": "research", "description": "Agent d'exploration & recherche (Read-Only)"},
    ]
    if rc == 0 and out:
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("name") or line.startswith("-"):
                continue
            parts = line.split(None, 1)
            name = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else "Agent personnalisé"
            if name and not any(a["name"] == name for a in agents):
                agents.append({"name": name, "description": desc})
    return agents


async def list_mcp_servers() -> List[Dict[str, str]]:
    """Parse `agy mcp list` into a structured list of MCP servers."""
    rc, out, _ = await run_agy_subcommand(["mcp", "list"], timeout=12.0)
    servers: List[Dict[str, str]] = []
    if rc != 0 or not out:
        return servers

    for line in out.splitlines():
        line_str = line.strip()
        if not line_str or line_str.upper().startswith("NAME") or line_str.startswith("---"):
            continue
        if "no configured" in line_str.lower() or "no mcp" in line_str.lower():
            continue
        parts = line_str.split(None, 3)
        if len(parts) >= 3:
            servers.append({
                "name": parts[0],
                "type": parts[1],
                "status": parts[2].lower(),
                "target": parts[3] if len(parts) > 3 else "",
            })
    return servers


async def toggle_mcp_server(name: str, enable: bool) -> Tuple[bool, str]:
    action = "enable" if enable else "disable"
    rc, out, err = await run_agy_subcommand(["mcp", action, name], timeout=12.0)
    msg = out or err or f"Serveur MCP '{name}' {'activé' if enable else 'désactivé'}."
    return (rc == 0), msg


async def remove_mcp_server(name: str) -> Tuple[bool, str]:
    rc, out, err = await run_agy_subcommand(["mcp", "remove", name], timeout=12.0)
    return (rc == 0), (out or err or f"Serveur MCP '{name}' supprimé.")


async def install_recommended_mcp_server(srv_id: str, env_value: Optional[str] = None) -> Tuple[bool, str]:
    """Install one of the curated RECOMMENDED_MCP_SERVERS via `agy mcp add`."""
    entry = next((s for s in config.RECOMMENDED_MCP_SERVERS if s["id"] == srv_id), None)
    if not entry:
        return False, f"Serveur MCP '{srv_id}' inconnu dans le catalogue."

    sub_args: List[str] = ["mcp", "add"]
    env_key = entry.get("env_key")
    if env_key:
        val = (env_value or os.getenv(env_key, "")).strip()
        if val:
            sub_args.extend(["--env", f"{env_key}={val}"])

    sub_args.extend([entry["id"], "--", entry["command"]] + list(entry["args"]))
    rc, out, err = await run_agy_subcommand(sub_args, timeout=20.0)
    msg = out or err or f"Serveur MCP '{entry['id']}' ajouté avec succès."
    return (rc == 0), msg


async def list_cli_plugins() -> Tuple[str, List[Dict[str, str]]]:
    """Run `agy plugin list` and return raw output plus parsed items."""
    rc, out, err = await run_agy_subcommand(["plugin", "list"], timeout=12.0)
    text = out or err or "Aucun plugin importé."
    items: List[Dict[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or "no imported" in s.lower() or s.upper().startswith("NAME") or s.startswith("-"):
            continue
        parts = s.split(None, 2)
        if parts:
            items.append({
                "name": parts[0],
                "status": parts[1].lower() if len(parts) > 1 else "enabled",
                "info": parts[2] if len(parts) > 2 else "",
            })
    return text, items


async def run_plugin_action(action: str, target: str = "") -> Tuple[bool, str]:
    args = ["plugin", action]
    if target:
        args.append(target)
    rc, out, err = await run_agy_subcommand(args, timeout=30.0)
    return (rc == 0), (out or err or f"Action plugin '{action}' terminée.")


async def manage_remote_control(action: str = "status") -> Tuple[bool, str]:
    """Run `agy remote-control status|start|stop`."""
    if action not in ("status", "start", "stop"):
        action = "status"
    rc, out, err = await run_agy_subcommand(["remote-control", action], timeout=20.0)
    return (rc == 0), (out or err or f"Remote-control {action} exécuté.")


async def update_cli_binary() -> Tuple[bool, str]:
    """Run `agy update` to self-update the Antigravity CLI."""
    rc, out, err = await run_agy_subcommand(["update"], timeout=60.0)
    return (rc == 0), (out or err or "Vérification de mise à jour Antigravity CLI terminée.")


class AgentRunner:
    def __init__(self):
        self.active_process: Optional[asyncio.subprocess.Process] = None
        self.is_running: bool = False
        self.has_active_session: bool = False
        self.active_conversation_id: Optional[str] = None
        self.always_allow_session: bool = False
        self.last_usage: Dict[str, Any] = {}
        self.session_total_tokens: int = 0
        self.session_turns: int = 0

    def reset_session(self) -> None:
        self.has_active_session = False
        self.active_conversation_id = None
        self.always_allow_session = False
        self.last_usage = {}
        self.session_total_tokens = 0
        self.session_turns = 0
        logger.info("Agent conversation session reset.")

    def set_conversation(self, conversation_id: str) -> None:
        self.active_conversation_id = conversation_id.strip()
        self.has_active_session = bool(self.active_conversation_id)
        logger.info(f"Switched active conversation to: {self.active_conversation_id}")

    async def abort(self) -> bool:
        if not self.active_process or not self.is_running:
            return False
        pid = self.active_process.pid
        try:
            logger.info(f"Aborting running agent process (PID={pid})...")
            if IS_WINDOWS:
                # Kill entire process tree on Windows safely
                try:
                    kill_proc = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/F",
                        "/T",
                        "/PID",
                        str(pid),
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await asyncio.wait_for(kill_proc.wait(), timeout=5.0)
                except Exception:
                    pass
                if self.active_process and self.active_process.returncode is None:
                    self.active_process.kill()
            else:
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGINT)
                    await asyncio.sleep(0.3)
                    if self.active_process and self.active_process.returncode is None:
                        os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    if self.active_process and self.active_process.returncode is None:
                        self.active_process.kill()
            return True
        except Exception as e:
            logger.warning(f"Error while killing process: {e}")
            try:
                if self.active_process:
                    self.active_process.kill()
                return True
            except Exception:
                return False
        finally:
            self.is_running = False
            self.active_process = None

    async def run_prompt_stream(
        self,
        prompt: str,
        settings: dict,
        on_update: Optional[Callable] = None,
        on_model_fallback: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
    ) -> Tuple[str, bool]:
        bin_path = find_agy_binary(config.AGY_BIN_PATH)
        if not bin_path:
            return (
                "❌ <b>Binaire Antigravity CLI (<code>agy</code>) introuvable sur le système.</b>\n"
                "Exécutez le script d'installation (<code>install.ps1</code> ou <code>install.sh</code>) "
                "pour l'installer automatiquement.",
                False,
            )

        # Ensure we have up-to-date models list
        available_models = await fetch_available_models(force_refresh=False)
        model_ids = [m[0] for m in available_models] or [m[0] for m in DEFAULT_MODELS_LIST]

        preferred_model = settings.get("model", "gemini-4-argon-medium")
        if preferred_model not in model_ids and model_ids:
            # Keep preferred_model first in case it's a valid alias, then all discovered models
            candidate_models = [preferred_model] + [m for m in model_ids if m != preferred_model]
        else:
            candidate_models = [preferred_model] + [m for m in model_ids if m != preferred_model]

        governor.start_turn()
        try:
            try:
                auto_extract_and_store_facts(prompt)
            except Exception as e:
                logger.debug(f"Auto memory extraction skipped: {e}")

            memory_ctx = get_relevant_context(prompt)
            group_ctx = group_mgr.get_groups_context_for_agent(prompt)
            system_prompt = build_system_prompt(settings)

            if self.has_active_session:
                prompt_parts = []
                if memory_ctx:
                    prompt_parts.append(memory_ctx.strip())
                if group_ctx:
                    prompt_parts.append(group_ctx.strip())
                prompt_parts.append(f"[USER PROMPT]\n{prompt}")
                enhanced_prompt = "\n\n".join(prompt_parts)
            else:
                prompt_parts = [system_prompt]
                if memory_ctx:
                    prompt_parts.append(memory_ctx.strip())
                if group_ctx:
                    prompt_parts.append(group_ctx.strip())
                prompt_parts.append(f"[USER PROMPT]\n{prompt}")
                enhanced_prompt = "\n\n".join(prompt_parts)

            last_error = ""

            for model_idx, current_model in enumerate(candidate_models[:5]):
                if model_idx > 0 and on_model_fallback:
                    try:
                        await on_model_fallback(candidate_models[model_idx - 1], current_model)
                    except Exception:
                        pass

                for attempt in range(2):
                    response_text, is_success, is_quota = await self._execute_model_stream(
                        bin_path=bin_path,
                        prompt=enhanced_prompt,
                        raw_user_prompt=prompt,
                        model=current_model,
                        settings=settings,
                        on_update=on_update,
                        on_tool_call=on_tool_call,
                        on_tool_result=on_tool_result,
                    )

                    if is_success:
                        self.has_active_session = True
                        return (response_text, True)

                    if is_quota:
                        logger.warning(
                            f"Quota limit reached on model '{current_model}'. Switching immediately to next fallback model..."
                        )
                        last_error = response_text
                        break

                    if response_text == "AUTO_RETRY_CONTINUE" and attempt == 0:
                        logger.info(f"Stream hiccup on {current_model}. Continuing session...")
                        self.has_active_session = True
                        await asyncio.sleep(1.0)
                        continue

                    # If --model was rejected (e.g. account has different model list or is not authenticated yet),
                    # retry immediately without `--model` so `agy` uses the account's default model or reports auth status.
                    err_lower = response_text.lower()
                    if current_model and (
                        "invalid model selection" in err_lower
                        or "not recognized as a known model" in err_lower
                    ):
                        logger.warning(
                            f"Model '{current_model}' rejected by CLI ({response_text[:120]}). "
                            "Retrying with CLI default model (no --model flag)..."
                        )
                        fallback_text, fb_ok, fb_quota = await self._execute_model_stream(
                            bin_path=bin_path,
                            prompt=enhanced_prompt,
                            raw_user_prompt=prompt,
                            model="",
                            settings=settings,
                            on_update=on_update,
                            on_tool_call=on_tool_call,
                            on_tool_result=on_tool_result,
                        )
                        if fb_ok:
                            self.has_active_session = True
                            return (fallback_text, True)
                        response_text = fallback_text
                        err_lower = response_text.lower()

                    if (
                        "authentication required" in err_lower
                        or "not authenticated" in err_lower
                        or "no model configuration is available for this account" in err_lower
                        or "not recognized as a known model" in err_lower
                    ):
                        auth_help = (
                            "🔐 <b>Authentification Google Antigravity CLI requise sur le serveur !</b>\n\n"
                            "Le binaire <code>agy</code> n'est pas encore connecté à votre compte Google (ou aucun modèle n'est rattaché à la session).\n\n"
                            "👉 <b>Comment vous connecter en 30 secondes (en SSH sur votre serveur) :</b>\n"
                            "1️⃣ Tapez la commande : <code>agy</code>\n"
                            "2️⃣ Ouvrez le lien Google affiché dans votre navigateur et connectez-vous.\n"
                            "3️⃣ Si votre navigateur redirige vers une page <code>http://localhost:...</code> inaccessible, "
                            "<b>copiez l'URL complète</b> depuis la barre d'adresse du navigateur et <b>collez-la dans le terminal SSH</b>.\n"
                            "4️⃣ Une fois l'interface <code>agy</code> ouverte, quittez avec <code>Ctrl+C</code> puis tapez :\n"
                            "<code>systemctl restart antigravity-bot</code>"
                        )
                        return (auth_help, False)

                    # Auto-recovery if --conversation / --continue failed due to corrupted/expired session
                    err_upper = response_text.upper()
                    if self.has_active_session and (
                        "INVALID_ARGUMENT" in err_upper
                        or "NOT_FOUND" in err_upper
                        or "400" in err_upper
                        or "CONVERSATION" in err_upper
                        or "SESSION" in err_upper
                    ):
                        logger.warning(f"Session recovery triggered ({response_text[:120]}). Resetting session...")
                        self.reset_session()
                        prompt_parts = [system_prompt]
                        if memory_ctx:
                            prompt_parts.append(memory_ctx.strip())
                        prompt_parts.append(f"[DEMANDE DE L'UTILISATEUR]\n{prompt}")
                        enhanced_prompt = "\n\n".join(prompt_parts)
                        continue

                    break

                last_error = response_text
                if not is_quota:
                    return (response_text, False)

                logger.warning(f"Quota reached for model {current_model}. Attempting fallback...")

            return (
                "💳 <b>Crédits / Quota temporairement atteints</b>\n\n"
                "Tous les modèles testés ont atteint leur limite de requêtes.\n"
                f"<pre>{last_error[:500]}</pre>",
                False,
            )
        finally:
            governor.end_turn()

    async def _execute_model_stream(
        self,
        bin_path: str,
        prompt: str,
        raw_user_prompt: str,
        model: str,
        settings: dict,
        on_update: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
    ) -> Tuple[str, bool, bool]:
        mode = settings.get("mode", "auto-approve")
        user_effort = settings.get("effort", "auto")
        timeout = int(settings.get("timeout", 600))
        sandbox = bool(settings.get("sandbox", False))
        agent_profile = settings.get("agent_profile", "").strip()
        remote_ctrl = bool(settings.get("remote_control", False))
        extra_dirs = settings.get("extra_dirs", []) or []
        ws_dir_str = settings.get("workspace_dir", str(config.WORKSPACE_DIR))
        ws_path = Path(ws_dir_str) if ws_dir_str else config.WORKSPACE_DIR
        if not ws_path.exists():
            ws_path = config.WORKSPACE_DIR

        is_infinite = (timeout <= 0)
        effective_print_timeout = 0 if is_infinite else timeout

        cmd = [bin_path]

        # Permission & Execution Mode
        if mode == "auto-approve" or self.always_allow_session:
            cmd.append("--dangerously-skip-permissions")
        elif mode == "plan":
            cmd.extend(["--mode", "plan"])
        else:
            cmd.extend(["--mode", "accept-edits"])

        if sandbox:
            cmd.append("--sandbox")

        if agent_profile:
            cmd.extend(["--agent", agent_profile])

        if model and model.lower() != "auto":
            cmd.extend(["--model", model])

        effort_flag = resolve_effort_flag(model, user_effort)
        if effort_flag:
            cmd.extend(["--effort", effort_flag])

        for d in extra_dirs:
            if d and Path(d).exists():
                cmd.extend(["--add-dir", str(Path(d).resolve())])

        if remote_ctrl:
            cmd.append("--remote-control")

        # Conversation continuity
        if self.has_active_session:
            if self.active_conversation_id:
                cmd.extend(["--conversation", self.active_conversation_id])
            else:
                cmd.append("--continue")

        # Protect against OS command-line length limits (especially Windows 32KB CreateProcess limit)
        temp_prompt_file: Optional[Path] = None
        effective_cli_prompt = prompt
        if len(prompt) > 12000:
            temp_prompt_file = TEMP_DIR / f"prompt_{os.getpid()}_{int(asyncio.get_event_loop().time())}.md"
            temp_prompt_file.write_text(prompt, encoding="utf-8")
            effective_cli_prompt = (
                f"Lis attentivement le fichier d'instructions `{temp_prompt_file}` avec `view_file` "
                f"et exécute intégralement la demande de l'utilisateur qui s'y trouve."
            )

        cmd.extend([
            "--output-format",
            "stream-json",
            "--print-timeout",
            f"{effective_print_timeout}s",
            "-p",
            effective_cli_prompt,
        ])

        logger.info(
            f"Executing agy stream (model={model or 'default'}, effort={effort_flag or 'auto'}, "
            f"mode={mode}, timeout={'infinite' if is_infinite else f'{timeout}s'})"
        )

        self.is_running = True
        accumulated_text: List[str] = []
        stderr_lines: List[str] = []
        current_action = f"🧠 Analyse en cours ({model or 'agy'})..."
        got_success_result = False
        pending_tool_calls: Dict[str, Dict[str, Any]] = {}
        active_subagents: Dict[str, str] = {}

        popen_kwargs: Dict[str, Any] = {
            "stdin": asyncio.subprocess.DEVNULL,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(ws_path),
            "env": _build_agy_env(),
        }
        if IS_WINDOWS:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = await asyncio.create_subprocess_exec(*cmd, **popen_kwargs)
            self.active_process = process

            line_queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=2000)
            ui_dirty = False
            ui_updater_running = True

            async def stdout_reader():
                try:
                    while True:
                        raw_bytes = await process.stdout.readline()
                        if not raw_bytes:
                            break
                        decoded = raw_bytes.decode("utf-8", errors="replace").strip()
                        if decoded:
                            await line_queue.put(decoded)
                except Exception as ex:
                    logger.debug(f"Stdout reader finished or interrupted: {ex}")
                finally:
                    await line_queue.put(None)

            async def stderr_reader():
                try:
                    while True:
                        raw_err = await process.stderr.readline()
                        if not raw_err:
                            break
                        decoded = raw_err.decode("utf-8", errors="replace").strip()
                        if decoded:
                            stderr_lines.append(decoded)
                            if len(stderr_lines) > 200:
                                stderr_lines.pop(0)
                except Exception as ex:
                    logger.debug(f"Stderr reader finished or interrupted: {ex}")

            async def ui_updater_task():
                nonlocal ui_dirty
                while ui_updater_running:
                    try:
                        await asyncio.sleep(1.5)
                        if on_update:
                            full_text = "".join(accumulated_text).strip()
                            await on_update(full_text, current_action)
                            ui_dirty = False
                    except asyncio.CancelledError:
                        break
                    except Exception as ue:
                        logger.debug(f"UI updater non-fatal error: {ue}")

            reader_task = asyncio.create_task(stdout_reader())
            stderr_task = asyncio.create_task(stderr_reader())
            updater_task = asyncio.create_task(ui_updater_task())

            def stop_stream_tasks():
                nonlocal ui_updater_running
                ui_updater_running = False
                for t in (updater_task, reader_task, stderr_task):
                    if not t.done():
                        t.cancel()

            if on_update:
                try:
                    await on_update("", current_action)
                except Exception:
                    pass

            while True:
                try:
                    if is_infinite:
                        raw_line = await line_queue.get()
                    else:
                        raw_line = await asyncio.wait_for(line_queue.get(), timeout=float(timeout))
                except asyncio.TimeoutError:
                    stop_stream_tasks()
                    await self.abort()
                    return (f"⏱️ Délai d'attente dépassé ({timeout}s).", False, False)

                if raw_line is None:
                    break

                try:
                    event = json.loads(raw_line)
                    evt_type = event.get("event")

                    if evt_type == "init":
                        conv_id = event.get("conversation_id")
                        if conv_id and not self.active_conversation_id:
                            self.active_conversation_id = conv_id

                    elif evt_type == "step_update":
                        su = event.get("step_update", {})
                        stype = su.get("step_type", "")
                        state = su.get("state", "")
                        sindex = su.get("step_index", 0)
                        step_conv_id = su.get("conversation_id", "")

                        is_subagent_step = bool(
                            step_conv_id
                            and self.active_conversation_id
                            and step_conv_id != self.active_conversation_id
                        )
                        sub_prefix = "🤖 [Sous-Agent] " if is_subagent_step else ""

                        if stype == "agent_response":
                            thinking_delta = su.get("thinking_delta", "") or su.get("thinking", "")
                            delta = su.get("text_delta", "")
                            if delta and not is_subagent_step:
                                accumulated_text.append(delta)
                                current_action = ""
                                ui_dirty = True
                            elif thinking_delta:
                                current_action = f"{sub_prefix}🧠 Réflexion approfondie en cours..."
                                ui_dirty = True
                            elif state == "ACTIVE" and not accumulated_text:
                                current_action = f"{sub_prefix}🧠 Analyse & Réflexion..."
                                ui_dirty = True

                        elif stype == "tool":
                            tool_name = su.get("tool_name") or su.get("tool_info", {}).get("name", "outil")
                            tool_info = su.get("tool_info", {}) or {}
                            tool_args = tool_info.get("parameters", {}) or tool_info.get("args", {}) or {}
                            call_id = f"{step_conv_id[:6]}_{sindex}" if step_conv_id else f"step_{sindex}"

                            if state == "ACTIVE":
                                action_desc = self._describe_tool_action(tool_name, tool_args, sub_prefix)
                                current_action = action_desc
                                pending_tool_calls[call_id] = {"name": tool_name, "args": tool_args}
                                if on_tool_call:
                                    try:
                                        await on_tool_call(tool_name, tool_args, call_id)
                                    except Exception:
                                        pass
                                ui_dirty = True

                            elif state == "DONE":
                                output = tool_info.get("output", "") or tool_info.get("result", "") or ""
                                is_err = su.get("is_error", False)
                                tool_info_call = pending_tool_calls.pop(call_id, {})
                                tool_name = tool_info_call.get("name", tool_name)
                                tool_args = tool_info_call.get("args", tool_args)
                                current_action = ""
                                if on_tool_result:
                                    try:
                                        await on_tool_result(tool_name, tool_args, str(output)[:500], call_id, is_err)
                                    except Exception:
                                        pass
                                ui_dirty = True

                    elif evt_type == "result":
                        res = event.get("result", {})
                        status = res.get("status")
                        conv_id = res.get("conversation_id")
                        if conv_id:
                            self.active_conversation_id = conv_id

                        usage = res.get("usage", {})
                        if usage:
                            self.last_usage = usage
                            total_tok = int(usage.get("total_tokens", 0))
                            self.session_total_tokens += total_tok
                            self.session_turns += int(res.get("num_turns", 1))
                            record_conversation(
                                conversation_id=self.active_conversation_id or "session",
                                prompt_preview=raw_user_prompt,
                                model=model,
                                tokens=total_tok,
                            )

                        if status == "SUCCESS":
                            final_resp = res.get("response", "")
                            if final_resp:
                                accumulated_text = [final_resp]
                            got_success_result = True
                            break
                        elif status == "ERROR":
                            err = res.get("error", "")
                            if is_quota_error(err):
                                stop_stream_tasks()
                                return (err, False, True)
                            if "subscriber fell behind" in err.lower() or "stalled" in err.lower():
                                logger.warning(f"Stream stall detected: {err}.")
                                final_text_so_far = "".join(accumulated_text).strip()
                                if final_text_so_far:
                                    got_success_result = True
                                    break
                                stop_stream_tasks()
                                return ("AUTO_RETRY_CONTINUE", False, False)

                            stop_stream_tasks()
                            return (f"Erreur: {err}", False, False)

                except json.JSONDecodeError:
                    # Non-JSON output line
                    if not raw_line.startswith("{"):
                        accumulated_text.append(raw_line + "\n")
                        ui_dirty = True

            stop_stream_tasks()

            final_text = "".join(accumulated_text).strip()
            if got_success_result or final_text:
                try:
                    if process.returncode is None:
                        process.terminate()
                except Exception:
                    pass
                return (final_text or "✅ Action exécutée avec succès.", True, False)

            stderr_text = "\n".join(stderr_lines).strip()
            combined_err = stderr_text or final_text or f"Code sortie {process.returncode}"
            if is_quota_error(combined_err):
                return (combined_err, False, True)
            return (f"⚠️ Erreur CLI : {combined_err}", False, False)

        except Exception as e:
            logger.error(f"Execution exception: {e}")
            return (f"❌ Erreur inattendue : {e}", False, False)
        finally:
            self.is_running = False
            proc_ref = self.active_process
            self.active_process = None
            if proc_ref is not None:
                try:
                    if proc_ref.returncode is None:
                        proc_ref.kill()
                    await asyncio.wait_for(proc_ref.wait(), timeout=2.0)
                except Exception:
                    pass
                try:
                    if hasattr(proc_ref, "_transport") and proc_ref._transport:
                        proc_ref._transport.close()
                except Exception:
                    pass
            if temp_prompt_file and temp_prompt_file.exists():
                try:
                    temp_prompt_file.unlink(missing_ok=True)
                except Exception:
                    pass

    @staticmethod
    def _describe_tool_action(tool_name: str, tool_args: dict, prefix: str = "") -> str:
        if tool_name == "run_command":
            cmd_line = tool_args.get("CommandLine", "")
            return f"{prefix}⚙️ Commande : {cmd_line[:60]}"
        if tool_name == "view_file":
            fpath = str(tool_args.get("AbsolutePath", "")).replace("\\", "/")
            return f"{prefix}📄 Lecture : {fpath.split('/')[-1]}"
        if tool_name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
            fpath = str(tool_args.get("TargetFile", "")).replace("\\", "/")
            return f"{prefix}✏️ Écriture : {fpath.split('/')[-1]}"
        if tool_name == "search_web":
            q = tool_args.get("query", "")
            return f"{prefix}🔍 Recherche Web : {q[:45]}"
        if tool_name == "read_url_content":
            u = tool_args.get("Url", "")
            return f"{prefix}🌐 Lecture URL : {u[:45]}"
        if tool_name == "generate_image":
            p = tool_args.get("ImageName") or tool_args.get("Prompt", "")
            return f"{prefix}🎨 Génération d'image : {str(p)[:40]}"
        if tool_name == "invoke_subagent":
            subs = tool_args.get("Subagents", [])
            if isinstance(subs, list) and subs:
                roles = ", ".join(str(s.get("Role", s.get("TypeName", "Agent"))) for s in subs[:3])
                return f"🤖 Lancement Sous-Agent(s) : {roles}"
            return "🤖 Lancement de Sous-Agent(s) en parallèle..."
        if tool_name == "define_subagent":
            name = tool_args.get("name", "custom")
            return f"🧩 Création du Sous-Agent spécialisé : {name}"
        if tool_name == "manage_subagents":
            act = tool_args.get("Action", "list")
            return f"🤖 Gestion des Sous-Agents ({act})..."
        if tool_name == "send_message":
            rec = str(tool_args.get("Recipient", ""))[:12]
            return f"💬 Message au Sous-Agent ({rec})..."
        if tool_name == "call_mcp_tool":
            srv = tool_args.get("ServerName", "MCP")
            tname = tool_args.get("ToolName", "")
            return f"{prefix}🔌 MCP [{srv}] : {tname}"
        if tool_name.startswith("browser_"):
            return f"{prefix}🌐 Navigateur : {tool_name.replace('browser_', '')}"
        return f"{prefix}🔧 Outil : {tool_name}"