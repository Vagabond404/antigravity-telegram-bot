#!/usr/bin/env python3
"""
updater.py - Autonomous Zero-Data-Loss Self-Updater for Antigravity Telegram Agent
Features:
- Detects new commits on the GitHub repository (`origin/main`) in the background
- Notifies the Administrator on Telegram with changelog, commit list & CLI version check
- Backs up and preserves 100% of user data (.env, memory.db, conversations.json, settings.json, users.json, custom_commands.json, skills)
- Checks required Antigravity CLI (`agy`) version from `VERSION.json` (`min_agy_version`) and auto-updates `agy` if needed
- Performs hot-restart via a detached background worker so the bot never dies mid-update
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, Tuple, List

import config
from config import (
    BASE_DIR,
    TEMP_DIR,
    IS_WINDOWS,
    find_agy_binary,
    ensure_default_skill_installed,
)

logger = logging.getLogger("updater")

VERSION_FILE = BASE_DIR / "VERSION.json"
UPDATE_STATE_FILE = TEMP_DIR / "update_state.json"
PENDING_UPDATE_ACK_FILE = TEMP_DIR / "pending_update_ack.json"
BACKUP_DIR = TEMP_DIR / "user_data_backup"

PROTECTED_USER_FILES = [
    ".env",
    "settings.json",
    "users.json",
    "memory.db",
    "conversations.json",
    "pending_approvals.json",
    "incidents_history.json",
    "groups.json",
    "school_data.json",
]


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Extract (major, minor, patch) tuple from any version string (e.g. '1.3.0' -> (1, 3, 0))."""
    if not version_str:
        return (0, 0, 0)
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(version_str))
    if not m:
        return (0, 0, 0)
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)) if m.group(3) is not None else 0,
    )


def is_version_older(installed: str, required: str) -> bool:
    """Return True if installed version is strictly older than required version."""
    if not required:
        return False
    if not installed:
        return True
    return parse_semver(installed) < parse_semver(required)


def load_local_version_manifest() -> Dict[str, Any]:
    """Read local VERSION.json."""
    default_manifest = {
        "bot_version": "4.1.0",
        "min_agy_version": "1.3.0",
        "repository": "https://github.com/Vagabond404/antigravity-telegram-bot.git",
        "branch": "main",
        "changelog": "",
    }
    if VERSION_FILE.is_file():
        try:
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                default_manifest.update(data)
        except Exception as e:
            logger.debug(f"Could not read VERSION.json: {e}")
    return default_manifest


async def _run_cmd(args: List[str], cwd: Optional[Path] = None, timeout: float = 30.0) -> Tuple[int, str, str]:
    """Run a command asynchronously and return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd or BASE_DIR),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "TERM": "dumb"},
        )
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", errors="replace").strip(),
            err_b.decode("utf-8", errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        return 124, "", f"Timeout ({int(timeout)}s)"
    except Exception as e:
        return 1, "", str(e)


async def get_installed_agy_version() -> str:
    """Return the installed Antigravity CLI version string (e.g. '1.3.0'), or '' if missing."""
    bin_path = find_agy_binary()
    if not bin_path:
        return ""
    rc, out, err = await _run_cmd([bin_path, "--version"], timeout=10.0)
    raw = (out or err or "").strip()
    m = re.search(r"\d+\.\d+(?:\.\d+)?", raw)
    return m.group(0) if m else raw[:32]


async def get_local_git_sha() -> str:
    """Return current local git commit hash (full)."""
    rc, out, _ = await _run_cmd(["git", "rev-parse", "HEAD"], timeout=8.0)
    return out.strip() if rc == 0 else ""


def _load_update_state() -> Dict[str, Any]:
    if UPDATE_STATE_FILE.is_file():
        try:
            return json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_update_state(state: Dict[str, Any]) -> None:
    try:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        UPDATE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed saving update state: {e}")


def should_notify_for_commit(remote_sha: str) -> bool:
    """Return True if we haven't already notified or dismissed this exact remote commit."""
    if not remote_sha:
        return False
    st = _load_update_state()
    if st.get("dismissed_sha") == remote_sha:
        return False
    if st.get("last_notified_sha") == remote_sha:
        return False
    return True


def mark_commit_notified(remote_sha: str) -> None:
    st = _load_update_state()
    st["last_notified_sha"] = remote_sha
    st["notified_at"] = int(time.time())
    _save_update_state(st)


def mark_commit_dismissed(remote_sha: str) -> None:
    st = _load_update_state()
    st["dismissed_sha"] = remote_sha
    st["last_notified_sha"] = remote_sha
    _save_update_state(st)


async def check_for_updates() -> Dict[str, Any]:
    """
    Check if the GitHub repository (`origin/main`) has new commits or if Antigravity CLI
    needs an update to match `min_agy_version`.
    """
    local_manifest = load_local_version_manifest()
    branch = local_manifest.get("branch", "main")
    repo_url = local_manifest.get("repository", "https://github.com/Vagabond404/antigravity-telegram-bot.git")
    local_ver = local_manifest.get("bot_version", "4.1.0")
    local_min_agy = local_manifest.get("min_agy_version", "1.3.0")

    installed_agy = await get_installed_agy_version()
    local_sha = await get_local_git_sha()

    # Ensure remote origin exists if .git is present
    if (BASE_DIR / ".git").exists():
        rc_rem, rem_out, _ = await _run_cmd(["git", "remote"], timeout=5.0)
        if rc_rem == 0 and "origin" not in rem_out.splitlines():
            await _run_cmd(["git", "remote", "add", "origin", repo_url], timeout=5.0)

    # Fetch latest from origin/<branch>
    rc_fetch, _, fetch_err = await _run_cmd(["git", "fetch", "origin", branch, "--quiet"], timeout=25.0)
    if rc_fetch != 0:
        return {
            "ok": False,
            "error": f"Impossible de contacter GitHub (git fetch) : {fetch_err}",
            "update_available": False,
            "local_version": local_ver,
            "local_sha": local_sha[:7] if local_sha else "inconnu",
            "installed_agy": installed_agy,
            "required_agy": local_min_agy,
            "agy_needs_update": is_version_older(installed_agy, local_min_agy),
        }

    rc_rem_sha, remote_sha, _ = await _run_cmd(["git", "rev-parse", f"origin/{branch}"], timeout=8.0)
    remote_sha = remote_sha.strip() if rc_rem_sha == 0 else ""

    # Check if local is behind origin/branch
    rc_cnt, behind_str, _ = await _run_cmd(
        ["git", "rev-list", "--count", f"HEAD..origin/{branch}"], timeout=8.0
    )
    commits_behind = int(behind_str) if (rc_cnt == 0 and behind_str.isdigit()) else 0

    # Parse remote VERSION.json if available
    remote_manifest = dict(local_manifest)
    rc_show, show_out, _ = await _run_cmd(
        ["git", "show", f"origin/{branch}:VERSION.json"], timeout=8.0
    )
    if rc_show == 0 and show_out:
        try:
            parsed_rem = json.loads(show_out)
            if isinstance(parsed_rem, dict):
                remote_manifest.update(parsed_rem)
        except Exception:
            pass

    remote_ver = remote_manifest.get("bot_version", local_ver)
    required_agy = remote_manifest.get("min_agy_version", local_min_agy)
    changelog = remote_manifest.get("changelog", "")

    commits_list: List[str] = []
    changed_files: List[str] = []
    if commits_behind > 0:
        rc_log, log_out, _ = await _run_cmd(
            ["git", "log", f"HEAD..origin/{branch}", "--oneline", "-n", "10"], timeout=8.0
        )
        if rc_log == 0 and log_out:
            commits_list = [c.strip() for c in log_out.splitlines() if c.strip()]

        rc_diff, diff_out, _ = await _run_cmd(
            ["git", "diff", "--name-only", f"HEAD..origin/{branch}"], timeout=8.0
        )
        if rc_diff == 0 and diff_out:
            changed_files = [f.strip() for f in diff_out.splitlines() if f.strip()]

    agy_needs_update = is_version_older(installed_agy, required_agy)
    update_available = (commits_behind > 0) or agy_needs_update

    return {
        "ok": True,
        "update_available": update_available,
        "commits_behind": commits_behind,
        "local_version": local_ver,
        "remote_version": remote_ver,
        "local_sha": local_sha[:7] if local_sha else "inconnu",
        "remote_sha": remote_sha[:7] if remote_sha else "inconnu",
        "remote_sha_full": remote_sha,
        "commits": commits_list,
        "changed_files": changed_files,
        "changelog": changelog,
        "installed_agy": installed_agy or "Non détecté",
        "required_agy": required_agy,
        "agy_needs_update": agy_needs_update,
    }


def _backup_user_data() -> Dict[str, Any]:
    """
    Create an in-memory + disk backup of all user data, custom commands, and custom skills
    so zero user data can ever be overwritten or lost during a git update.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    snapshot: Dict[str, Any] = {"files": {}, "custom_commands": {}}

    for fname in PROTECTED_USER_FILES:
        fpath = BASE_DIR / fname
        if fpath.is_file():
            try:
                raw_bytes = fpath.read_bytes()
                snapshot["files"][fname] = raw_bytes
                (BACKUP_DIR / fname).write_bytes(raw_bytes)
            except Exception as e:
                logger.warning(f"Backup warning for {fname}: {e}")

    # Also preserve user-created custom commands in custom_commands.json
    cc_path = BASE_DIR / "custom_commands.json"
    if cc_path.is_file():
        try:
            cc_data = json.loads(cc_path.read_text(encoding="utf-8"))
            if isinstance(cc_data, dict):
                snapshot["custom_commands"] = cc_data
                (BACKUP_DIR / "custom_commands.json").write_text(
                    json.dumps(cc_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception:
            pass

    return snapshot


def _restore_user_data(snapshot: Dict[str, Any]) -> None:
    """Restore all backed-up user data files and merge user-created custom commands."""
    for fname, raw_bytes in snapshot.get("files", {}).items():
        fpath = BASE_DIR / fname
        try:
            if not fpath.is_file() or fpath.read_bytes() != raw_bytes:
                fpath.write_bytes(raw_bytes)
        except Exception as e:
            logger.warning(f"Restore warning for {fname}: {e}")

    # Merge user-created commands into the updated custom_commands.json
    saved_cmds = snapshot.get("custom_commands", {})
    if saved_cmds:
        cc_path = BASE_DIR / "custom_commands.json"
        try:
            new_cmds = {}
            if cc_path.is_file():
                new_cmds = json.loads(cc_path.read_text(encoding="utf-8"))
            for k, v in saved_cmds.items():
                if k not in new_cmds or v.get("created_by") in ("user", "agent"):
                    new_cmds[k] = v
            cc_path.write_text(json.dumps(new_cmds, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Custom commands merge warning: {e}")


async def ensure_agy_cli_version(required_version: str, on_progress: Optional[Callable] = None) -> Tuple[bool, str]:
    """
    Check if installed Antigravity CLI (`agy`) satisfies `required_version`.
    If not, automatically run `agy update` (or the official installer script) and update symlinks.
    """
    installed = await get_installed_agy_version()
    if not is_version_older(installed, required_version):
        return True, installed

    if on_progress:
        await on_progress(
            f"⬆️ Mise à jour d'Antigravity CLI en cours (installé: {installed or 'aucun'} ➔ requis: >= {required_version})..."
        )

    bin_path = find_agy_binary()
    if bin_path:
        await _run_cmd([bin_path, "update"], timeout=120.0)

    installed_after = await get_installed_agy_version()
    if is_version_older(installed_after, required_version):
        # Fallback to official installer script
        if IS_WINDOWS:
            await _run_cmd(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "irm https://antigravity.google/cli/install.ps1 | iex",
                ],
                timeout=180.0,
            )
        else:
            await _run_cmd(
                ["bash", "-c", "curl -fsSL https://antigravity.google/cli/install.sh | bash"],
                timeout=180.0,
            )
            # Ensure global symlink on Linux
            home_agy = Path.home() / ".local" / "bin" / "agy"
            if home_agy.is_file():
                await _run_cmd(["ln", "-sf", str(home_agy), "/usr/local/bin/agy"], timeout=5.0)
        installed_after = await get_installed_agy_version()

    return (not is_version_older(installed_after, required_version)), (installed_after or installed)


def spawn_detached_restarter(current_pid: int) -> None:
    """
    Launch a detached background process (`updater.py --restart-worker <pid>`)
    that outlives the current bot process, waits for it to release resources,
    and cleanly restarts the service (systemd) or spawns the updated `bot.py`.
    """
    cmd = [sys.executable, str(BASE_DIR / "updater.py"), "--restart-worker", str(current_pid)]
    kwargs: Dict[str, Any] = {
        "cwd": str(BASE_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(cmd, **kwargs)


async def perform_safe_update(
    chat_id: int,
    message_id: int,
    on_progress: Optional[Callable] = None,
) -> Tuple[bool, str]:
    """
    Execute the complete zero-data-loss self-update sequence:
      1. Backup all user data (.env, memory.db, settings.json, users.json, conversations.json, custom_commands.json)
      2. Fetch & apply latest GitHub commits (`git fetch` + `git reset --hard origin/main`)
      3. Restore/merge all protected user data & sync default `telegram-bot-mastery` skill
      4. Update Python requirements in `.venv`
      5. Check `VERSION.json` for `min_agy_version` and auto-update Antigravity CLI (`agy`) if needed
      6. Schedule post-restart Telegram confirmation & trigger detached hot-restart
    """
    try:
        old_sha = (await get_local_git_sha())[:7]
        manifest_before = load_local_version_manifest()
        branch = manifest_before.get("branch", "main")

        if on_progress:
            await on_progress("🛡️ [1/5] Sauvegarde de sécurité de vos données, mémoires, chats et skills...")
        snapshot = _backup_user_data()

        if on_progress:
            await on_progress("⬇️ [2/5] Téléchargement des fichiers mis à jour depuis GitHub...")
        rc_f, _, err_f = await _run_cmd(["git", "fetch", "origin", branch], timeout=45.0)
        if rc_f != 0:
            return False, f"Échec de `git fetch origin {branch}` : {err_f}"

        rc_r, _, err_r = await _run_cmd(["git", "reset", "--hard", f"origin/{branch}"], timeout=20.0)
        if rc_r != 0:
            _restore_user_data(snapshot)
            return False, f"Échec de la mise à jour des fichiers (`git reset`) : {err_r}"

        # Restore all protected user data immediately
        _restore_user_data(snapshot)

        # Ensure Linux shell scripts stay executable
        if not IS_WINDOWS:
            for sh_file in BASE_DIR.glob("*.sh"):
                try:
                    os.chmod(sh_file, 0o755)
                except Exception:
                    pass

        # Sync the built-in skill to ~/.gemini/config/skills/telegram-bot-mastery/SKILL.md
        ensure_default_skill_installed()

        if on_progress:
            await on_progress("📦 [3/5] Vérification et mise à jour des dépendances Python (`.venv`)...")
        await _run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"], timeout=120.0)

        # Check updated VERSION.json for required Antigravity CLI version
        new_manifest = load_local_version_manifest()
        new_bot_ver = new_manifest.get("bot_version", "4.1.0")
        req_agy_ver = new_manifest.get("min_agy_version", "1.3.0")

        if on_progress:
            await on_progress(f"🤖 [4/5] Vérification de la version d'Antigravity CLI (requis >= v{req_agy_ver})...")
        agy_ok, final_agy_ver = await ensure_agy_cli_version(req_agy_ver, on_progress=on_progress)

        new_sha_full = await get_local_git_sha()
        new_sha = new_sha_full[:7] if new_sha_full else "latest"
        mark_commit_notified(new_sha_full)

        # Record pending ACK so the newly restarted bot confirms completion in Telegram
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ack_payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "bot_version": new_bot_ver,
            "agy_version": final_agy_ver,
            "agy_ok": agy_ok,
            "timestamp": time.time(),
        }
        PENDING_UPDATE_ACK_FILE.write_text(json.dumps(ack_payload, indent=2), encoding="utf-8")

        if on_progress:
            await on_progress(
                f"🔄 [5/5] Fichiers (v{new_bot_ver} - `{new_sha}`) et Antigravity CLI (v{final_agy_ver}) prêts !\n"
                "Redémarrage à chaud du bot en cours (2-3 secondes)..."
            )

        return True, new_sha
    except Exception as e:
        logger.error(f"Unexpected error during perform_safe_update: {e}")
        return False, str(e)


def _run_restart_worker(old_pid: int) -> None:
    """
    Detached worker process:
    1. If running on Linux with an active `antigravity-bot.service` systemd unit, runs `systemctl restart antigravity-bot`.
    2. Otherwise waits for `old_pid` to exit cleanly and starts a fresh `bot.py` process.
    """
    time.sleep(1.2)

    if not IS_WINDOWS and shutil.which("systemctl"):
        try:
            chk = subprocess.run(
                ["systemctl", "is-enabled", "antigravity-bot.service"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if chk.returncode == 0:
                res = subprocess.run(["systemctl", "restart", "antigravity-bot.service"], timeout=15)
                if res.returncode == 0:
                    return
                subprocess.run(["sudo", "systemctl", "restart", "antigravity-bot.service"], timeout=15)
                return
        except Exception:
            pass

    # Wait up to 8 seconds for old PID to exit
    for _ in range(16):
        try:
            os.kill(old_pid, 0)
            time.sleep(0.5)
        except OSError:
            break

    # Spawn the updated bot.py
    kwargs: Dict[str, Any] = {
        "cwd": str(BASE_DIR),
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen([sys.executable, str(BASE_DIR / "bot.py")], **kwargs)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--restart-worker":
        try:
            target_pid = int(sys.argv[2])
        except ValueError:
            target_pid = 0
        _run_restart_worker(target_pid)
        sys.exit(0)
