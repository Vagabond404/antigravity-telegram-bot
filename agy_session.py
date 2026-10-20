"""
agy_session.py - Persistent Antigravity CLI Session Manager (stream-json)
Maintains a warm, persistent `agy` process running via stdin/stdout stream-json.
Eliminates process spawn/teardown overhead, enables prompt cache hits,
provides strict 1-turn-at-a-time request queueing, and guarantees crash-resilience.
"""

import os
import sys
import json
import signal
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List

import config
from config import BASE_DIR, IS_WINDOWS, find_agy_binary, record_conversation

logger = logging.getLogger("agy_session")

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


def is_quota_error(error_msg: str) -> bool:
    if not error_msg:
        return False
    lower = str(error_msg).lower()
    return any(k in lower for k in QUOTA_ERROR_KEYWORDS)


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
        env.setdefault("SSH_CONNECTION", "1")
        env.setdefault("NODE_OPTIONS", "--dns-result-order=ipv4first")
    return env


class AgySession:
    """
    Manages a single long-lived `agy` process communicating via NDJSON (stream-json).
    Thread-safe and async-safe request queueing ensures only 1 turn executes at a time.
    """

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._turn_in_progress: bool = False
        self._current_model: str = ""
        self._current_mode: str = "auto-approve"
        self._current_effort: str = "auto"
        self._current_workspace: Path = config.WORKSPACE_DIR
        self._active_conversation_id: Optional[str] = None
        self._has_active_session: bool = False

        # Session metrics
        self.last_usage: Dict[str, Any] = {}
        self.session_total_tokens: int = 0
        self.session_turns: int = 0

        # Background reader task
        self._stdout_reader_task: Optional[asyncio.Task] = None
        self._stderr_reader_task: Optional[asyncio.Task] = None
        self._event_queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()
        self._stderr_buffer: List[str] = []

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def is_running(self) -> bool:
        return self._turn_in_progress

    @property
    def active_conversation_id(self) -> Optional[str]:
        return self._active_conversation_id

    @property
    def has_active_session(self) -> bool:
        return self._has_active_session

    @has_active_session.setter
    def has_active_session(self, val: bool) -> None:
        self._has_active_session = bool(val)

    def set_conversation(self, conversation_id: str) -> None:
        self._active_conversation_id = conversation_id.strip() if conversation_id else None
        self._has_active_session = bool(self._active_conversation_id)
        logger.info(f"Switched session conversation to: {self._active_conversation_id}")

    def reset_session(self) -> None:
        self._has_active_session = False
        self._active_conversation_id = None
        self.last_usage = {}
        self.session_total_tokens = 0
        self.session_turns = 0
        logger.info("Agy persistent session reset.")

    async def ensure_warm_process(self, settings: dict, force_restart: bool = False) -> bool:
        """
        Start or verify the warm `agy` background process.
        Restarts if configuration changed (e.g. model or mode).
        """
        model = settings.get("model", "gemini-3.8-flash-low")
        if model == "auto" or not model:
            model = "gemini-3.8-flash-low"
        mode = settings.get("mode", "auto-approve")
        effort = settings.get("effort", "auto")
        ws_dir = Path(settings.get("workspace_dir", str(config.WORKSPACE_DIR)))

        needs_restart = (
            force_restart
            or not self.is_alive
            or (self._current_model and self._current_model != model)
            or (self._current_mode and self._current_mode != mode)
        )

        if not needs_restart:
            return True

        await self._stop_process()

        bin_path = find_agy_binary(config.AGY_BIN_PATH)
        if not bin_path:
            logger.error("Antigravity binary (agy) not found!")
            return False

        cmd = [
            bin_path,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--model",
            model,
            "--print-timeout",
            "0s",
            "--print",
            "",
        ]

        if mode == "auto-approve":
            cmd.append("--dangerously-skip-permissions")
        elif mode == "plan":
            cmd.extend(["--mode", "plan"])
        else:
            cmd.extend(["--mode", "accept-edits"])

        if settings.get("sandbox", False):
            cmd.append("--sandbox")

        if effort and effort != "auto" and effort in ("low", "medium", "high", "xhigh", "max"):
            cmd.extend(["--effort", effort])

        if self._active_conversation_id:
            cmd.extend(["--conversation", self._active_conversation_id])

        ws = ws_dir if ws_dir.exists() else config.WORKSPACE_DIR

        popen_kwargs: Dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(ws),
            "env": _build_agy_env(),
        }
        if IS_WINDOWS:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            logger.info(f"Spawning warm agy session: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(*cmd, **popen_kwargs)
            self._process = proc
            self._current_model = model
            self._current_mode = mode
            self._current_effort = effort
            self._current_workspace = ws
            self._stderr_buffer = []

            # Launch async stream reader tasks
            self._event_queue = asyncio.Queue(maxsize=10000)
            self._stdout_reader_task = asyncio.create_task(self._stdout_loop(proc))
            self._stderr_reader_task = asyncio.create_task(self._stderr_loop(proc))

            # Wait for init event with a short timeout
            init_event = await self._wait_for_init_event(timeout=15.0)
            if init_event:
                conv_id = init_event.get("conversation_id")
                if conv_id and not self._active_conversation_id:
                    self._active_conversation_id = conv_id
                logger.info(f"Warm agy session initialized successfully (conv_id={conv_id})")
                return True
            else:
                logger.warning("No init event received from agy session; proceeding anyway.")
                return True

        except Exception as e:
            logger.error(f"Failed to start warm agy session: {e}")
            await self._stop_process()
            return False

    async def _wait_for_init_event(self, timeout: float = 15.0) -> Optional[dict]:
        """Read until the first 'init' event or timeout."""
        t_end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < t_end:
            try:
                item = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                if item is None:
                    break
                if item.get("event") == "init":
                    return item
                # Put back non-init items
                await self._event_queue.put(item)
            except asyncio.TimeoutError:
                if not self.is_alive:
                    break
                continue
        return None

    async def _stdout_loop(self, proc: asyncio.subprocess.Process):
        """Continuously read NDJSON lines from stdout and dispatch to queue."""
        try:
            while proc.returncode is None and proc.stdout:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                raw_str = line_bytes.decode("utf-8", errors="replace").strip()
                if not raw_str:
                    continue
                try:
                    data = json.loads(raw_str)
                    await self._event_queue.put(data)
                except json.JSONDecodeError:
                    # Non-json output fallback
                    await self._event_queue.put({"event": "raw_output", "text": raw_str})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Agy session stdout loop ended: {e}")
        finally:
            await self._event_queue.put(None)

    async def _stderr_loop(self, proc: asyncio.subprocess.Process):
        """Continuously collect stderr messages."""
        try:
            while proc.returncode is None and proc.stderr:
                err_bytes = await proc.stderr.readline()
                if not err_bytes:
                    break
                err_str = err_bytes.decode("utf-8", errors="replace").strip()
                if err_str:
                    self._stderr_buffer.append(err_str)
                    if len(self._stderr_buffer) > 200:
                        self._stderr_buffer.pop(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Agy session stderr loop ended: {e}")

    async def _stop_process(self):
        """Terminate active agy process cleanly."""
        for t in (self._stdout_reader_task, self._stderr_reader_task):
            if t and not t.done():
                t.cancel()

        proc = self._process
        self._process = None
        self._turn_in_progress = False

        if proc is not None and proc.returncode is None:
            logger.info(f"Terminating agy session process PID={proc.pid}...")
            try:
                if IS_WINDOWS:
                    try:
                        kill_proc = await asyncio.create_subprocess_exec(
                            "taskkill", "/F", "/T", "/PID", str(proc.pid),
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await asyncio.wait_for(kill_proc.wait(), timeout=3.0)
                    except Exception:
                        pass
                    if proc.returncode is None:
                        proc.kill()
                else:
                    try:
                        pgid = os.getpgid(proc.pid)
                        os.killpg(pgid, signal.SIGINT)
                        await asyncio.sleep(0.2)
                        if proc.returncode is None:
                            os.killpg(pgid, signal.SIGKILL)
                    except Exception:
                        if proc.returncode is None:
                            proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except Exception as e:
                logger.debug(f"Process termination detail: {e}")

    async def abort(self) -> bool:
        """Interrupt and abort current execution immediately."""
        if not self._turn_in_progress and not self.is_alive:
            return False
        logger.warning("User requested turn abort. Stopping persistent agy session...")
        await self._stop_process()
        self._turn_in_progress = False
        return True

    async def execute_turn(
        self,
        prompt: str,
        settings: dict,
        on_update: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
        timeout: float = 600.0,
    ) -> Tuple[str, bool, bool]:
        """
        Execute one prompt turn on the persistent agy process.
        Returns: (final_response_text, is_success, is_quota_error)
        """
        async with self._lock:
            self._turn_in_progress = True
            try:
                ok = await self.ensure_warm_process(settings)
                if not ok or not self.is_alive or not self._process or not self._process.stdin:
                    return ("❌ Impossible d'initialiser la session Antigravity CLI.", False, False)

                # Format user input payload according to agy stream-json spec
                input_payload = {
                    "event": "user",
                    "message": {
                        "content": prompt
                    }
                }
                raw_payload = json.dumps(input_payload, ensure_ascii=False) + "\n"

                # Send turn payload
                self._process.stdin.write(raw_payload.encode("utf-8"))
                await self._process.stdin.drain()

                accumulated_text: List[str] = []
                final_response: str = ""
                got_success = False
                current_action = "🧠 Analyse en cours..."
                pending_tools: Dict[str, Dict[str, Any]] = {}
                t_start = asyncio.get_event_loop().time()
                ui_last_rendered = ""

                # Background task to push periodic UI updates
                ui_active = True

                async def ui_push_task():
                    nonlocal ui_last_rendered
                    while ui_active:
                        try:
                            await asyncio.sleep(2.0)
                            if on_update:
                                full = "".join(accumulated_text).strip()
                                if full != ui_last_rendered or current_action:
                                    ui_last_rendered = full
                                    await on_update(full, current_action)
                        except asyncio.CancelledError:
                            break
                        except Exception as ex:
                            logger.debug(f"UI push task non-fatal: {ex}")

                ui_task = asyncio.create_task(ui_push_task())

                try:
                    while True:
                        remaining_time = timeout - (asyncio.get_event_loop().time() - t_start)
                        if remaining_time <= 0 and timeout > 0:
                            await self.abort()
                            return (f"⏱️ Délai d'attente dépassé ({int(timeout)}s).", False, False)

                        wait_sec = min(max(1.0, remaining_time), 30.0) if timeout > 0 else 30.0
                        try:
                            event = await asyncio.wait_for(self._event_queue.get(), timeout=wait_sec)
                        except asyncio.TimeoutError:
                            if not self.is_alive:
                                break
                            continue

                        if event is None:
                            # Stream EOF
                            break

                        evt_type = event.get("event")

                        if evt_type == "init":
                            cid = event.get("conversation_id")
                            if cid:
                                self._active_conversation_id = cid

                        elif evt_type == "step_update":
                            su = event.get("step_update", {})
                            stype = su.get("step_type", "")
                            state = su.get("state", "")
                            sindex = su.get("step_index", 0)
                            step_cid = su.get("conversation_id", "")
                            is_subagent = bool(
                                step_cid
                                and self._active_conversation_id
                                and step_cid != self._active_conversation_id
                            )
                            sub_prefix = "🤖 [Sous-Agent] " if is_subagent else ""

                            if stype == "agent_response":
                                delta = su.get("text_delta", "")
                                thinking = su.get("thinking_delta", "") or su.get("thinking", "")
                                if delta and not is_subagent:
                                    accumulated_text.append(delta)
                                    current_action = ""
                                elif thinking:
                                    current_action = f"{sub_prefix}🧠 Réflexion approfondie en cours..."
                                elif state == "ACTIVE" and not accumulated_text:
                                    current_action = f"{sub_prefix}🧠 Analyse & Réflexion..."

                            elif stype == "tool":
                                tool_name = su.get("tool_name") or su.get("tool_info", {}).get("name", "outil")
                                tool_info = su.get("tool_info", {}) or {}
                                tool_args = tool_info.get("parameters", {}) or tool_info.get("args", {}) or {}
                                call_id = f"{step_cid[:6]}_{sindex}" if step_cid else f"step_{sindex}"

                                if state == "ACTIVE":
                                    current_action = self._format_tool_action(tool_name, tool_args, sub_prefix)
                                    pending_tools[call_id] = {"name": tool_name, "args": tool_args}
                                    if on_tool_call:
                                        try:
                                            await on_tool_call(tool_name, tool_args, call_id)
                                        except Exception:
                                            pass

                                elif state == "DONE":
                                    output = tool_info.get("output", "") or tool_info.get("result", "") or ""
                                    is_err = su.get("is_error", False)
                                    p_tool = pending_tools.pop(call_id, {})
                                    tool_name = p_tool.get("name", tool_name)
                                    tool_args = p_tool.get("args", tool_args)
                                    current_action = ""
                                    if on_tool_result:
                                        try:
                                            await on_tool_result(tool_name, tool_args, str(output)[:500], call_id, is_err)
                                        except Exception:
                                            pass

                        elif evt_type == "result":
                            res = event.get("result", {})
                            status = res.get("status")
                            cid = res.get("conversation_id")
                            if cid:
                                self._active_conversation_id = cid

                            usage = res.get("usage", {})
                            if usage:
                                self.last_usage = usage
                                total_tok = int(usage.get("total_tokens", 0))
                                self.session_total_tokens += total_tok
                                self.session_turns += int(res.get("num_turns", 1))
                                record_conversation(
                                    conversation_id=self._active_conversation_id or "warm_session",
                                    prompt_preview=prompt[:120],
                                    model=self._current_model,
                                    tokens=total_tok,
                                )
                                try:
                                    from quota_manager import quota_mgr
                                    quota_mgr.record_usage(self._current_model or "agy", total_tok)
                                except Exception:
                                    pass

                            if status == "SUCCESS":
                                resp = res.get("response", "")
                                if resp:
                                    final_response = resp
                                else:
                                    final_response = "".join(accumulated_text).strip()
                                got_success = True
                                break
                            elif status == "ERROR":
                                err = res.get("error", "")
                                if is_quota_error(err):
                                    return (err, False, True)
                                return (f"Erreur Antigravity : {err}", False, False)

                        elif evt_type == "raw_output":
                            raw_txt = event.get("text", "")
                            if raw_txt and not raw_txt.startswith("{"):
                                accumulated_text.append(raw_txt + "\n")

                finally:
                    ui_active = False
                    if not ui_task.done():
                        ui_task.cancel()

                final_text = final_response or "".join(accumulated_text).strip()
                if got_success or final_text:
                    self._has_active_session = True
                    return (final_text or "✅ Action exécutée avec succès.", True, False)

                stderr_text = "\n".join(self._stderr_buffer).strip()
                err_msg = stderr_text or "Le processus agy s'est interrompu sans réponse."
                if is_quota_error(err_msg):
                    return (err_msg, False, True)
                return (f"⚠️ Erreur CLI : {err_msg}", False, False)

            except Exception as e:
                logger.error(f"Exception during execute_turn: {e}", exc_info=True)
                return (f"❌ Erreur inattendue : {e}", False, False)
            finally:
                self._turn_in_progress = False

    @staticmethod
    def _format_tool_action(tool_name: str, tool_args: dict, prefix: str = "") -> str:
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
            return f"🧩 Définition du Sous-Agent : {name}"
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


# Singleton instance
agy_session = AgySession()
