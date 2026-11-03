"""
scheduler_manager.py - Native Scheduled Tasks & Autonomous Background Automations
Enables the AI Agent and the user to natively schedule one-shot timers and recurring cron jobs.
Executes prompts, scripts, or reminders and reports results directly to Telegram.
"""

import os
import re
import sys
import json
import time
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import BASE_DIR, WORKSPACE_DIR, IS_WINDOWS

logger = logging.getLogger("scheduler_manager")

DB_PATH = str(BASE_DIR / "scheduled_tasks.db")


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            task_type TEXT NOT NULL DEFAULT 'once',       -- once, interval, cron
            schedule_expr TEXT NOT NULL,                  -- in 30m, 18:00, 0 9 * * *, every 2h
            action_type TEXT NOT NULL DEFAULT 'prompt',   -- prompt, command, reminder
            payload TEXT NOT NULL,                        -- prompt text, shell command, or reminder
            chat_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',        -- active, paused, completed, failed
            next_run_ts REAL NOT NULL DEFAULT 0,
            last_run_ts REAL NOT NULL DEFAULT 0,
            run_count INTEGER NOT NULL DEFAULT 0,
            last_result TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON scheduled_tasks(status, next_run_ts);")
    conn.commit()
    return conn


def parse_schedule_expression(expr: str, base_time: Optional[float] = None) -> Tuple[str, float, Optional[int]]:
    """
    Parse natural language schedule expression into (task_type, next_run_timestamp, interval_seconds).
    Supports:
      - 'in 30m', '+30m', 'dans 15 minutes', 'in 2 hours', '+2h', 'in 1 day'
      - '18:00', 'at 18:30', 'à 20h00', 'tomorrow 09:00', 'demain à 10h'
      - 'every 30m', 'toutes les 2h', 'every 1d'
      - Cron expressions: '0 9 * * *'
    Returns: (task_type, next_run_ts, interval_seconds)
    """
    now = base_time if base_time is not None else time.time()
    clean = expr.strip().lower()

    # 1. Interval expressions ("every 30m", "toutes les 2h", "every 1d")
    m_int = re.search(r"(?:every|toutes?\s+les?)\s+(\d+)\s*(m(?:in)?|h(?:eure)?|d(?:ay)?|j(?:our)?)", clean)
    if m_int:
        qty = int(m_int.group(1))
        unit = m_int.group(2)[0]
        if unit == "m":
            interval = qty * 60
        elif unit == "h":
            interval = qty * 3600
        else: # d or j
            interval = qty * 86400
        return ("interval", now + interval, interval)

    # 2. Relative offsets ("in 30m", "+30m", "dans 10 minutes", "in 2 hours", "+2h")
    m_rel = re.search(r"(?:in|dans|\+)?\s*(\d+)\s*(m(?:inutes?)?|h(?:eures?)?|d(?:ays?)?|j(?:ours?)?|s(?:ec)?)", clean)
    if m_rel:
        qty = int(m_rel.group(1))
        unit = m_rel.group(2)[0]
        if unit == "s":
            offset = qty
        elif unit == "m":
            offset = qty * 60
        elif unit == "h":
            offset = qty * 3600
        else:
            offset = qty * 86400
        return ("once", now + offset, None)

    # 3. Fixed time of day ("18:00", "at 18:30", "à 20h30", "demain à 09:00")
    m_time = re.search(r"(?:at|à)?\s*(\d{1,2})[h:](\d{2})", clean)
    if m_time:
        hour = int(m_time.group(1))
        minute = int(m_time.group(2))
        dt_now = datetime.now()
        target_dt = dt_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if "demain" in clean or "tomorrow" in clean or target_dt <= dt_now:
            target_dt += timedelta(days=1)
        return ("once", target_dt.timestamp(), None)

    # 4. Cron expression (e.g. "0 9 * * *")
    parts = clean.split()
    if len(parts) == 5:
        try:
            from croniter import croniter
            cron = croniter(clean, datetime.now())
            next_dt = cron.get_next(datetime)
            return ("cron", next_dt.timestamp(), None)
        except Exception:
            pass

    # Default fallback: 1 hour from now
    return ("once", now + 3600, 3600)


def compute_next_run(task_type: str, schedule_expr: str, last_run: float) -> Optional[float]:
    """Compute subsequent run timestamp for recurring tasks."""
    now = time.time()
    clean = schedule_expr.strip().lower()

    if task_type == "interval":
        _, next_ts, _ = parse_schedule_expression(schedule_expr, base_time=now)
        return next_ts
    elif task_type == "cron":
        try:
            from croniter import croniter
            cron = croniter(schedule_expr, datetime.now())
            return cron.get_next(datetime).timestamp()
        except Exception:
            return now + 86400
    return None


def add_task(
    name: str,
    schedule_expr: str,
    payload: str,
    action_type: str = "prompt",
    chat_id: int = 0,
    db_path: str = DB_PATH,
) -> int:
    """Create a new scheduled task."""
    clean_name = (name or "").strip() or f"Task_{int(time.time())}"
    clean_payload = (payload or "").strip()
    clean_action = (action_type or "prompt").strip().lower()

    if not clean_payload:
        return 0

    clean_chat_id = int(chat_id or 0)

    task_type, next_ts, _ = parse_schedule_expression(schedule_expr)

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scheduled_tasks (name, task_type, schedule_expr, action_type, payload, chat_id, status, next_run_ts)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
    """, (clean_name, task_type, schedule_expr, clean_action, clean_payload, clean_chat_id, next_ts))
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Created scheduled task #{tid} '{clean_name}' (type: {task_type}, next: {datetime.fromtimestamp(next_ts)})")
    return int(tid or 0)


def list_tasks(status: Optional[str] = None, chat_id: Optional[int] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """List scheduled tasks, optionally filtered by status or chat."""
    conn = get_db(db_path)
    cur = conn.cursor()
    query = "SELECT id, name, task_type, schedule_expr, action_type, payload, chat_id, status, next_run_ts, last_run_ts, run_count, last_result, created_at FROM scheduled_tasks"
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if chat_id:
        conditions.append("chat_id = ?")
        params.append(int(chat_id))
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY status ASC, next_run_ts ASC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "task_type": r[2],
            "schedule_expr": r[3],
            "action_type": r[4],
            "payload": r[5],
            "chat_id": r[6],
            "status": r[7],
            "next_run_ts": r[8],
            "last_run_ts": r[9],
            "run_count": r[10],
            "last_result": r[11] or "",
            "created_at": r[12],
        }
        for r in rows
    ]


def get_task(task_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, task_type, schedule_expr, action_type, payload, chat_id, status, next_run_ts, last_run_ts, run_count, last_result, created_at
        FROM scheduled_tasks WHERE id = ?
    """, (task_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "task_type": row[2],
        "schedule_expr": row[3],
        "action_type": row[4],
        "payload": row[5],
        "chat_id": row[6],
        "status": row[7],
        "next_run_ts": row[8],
        "last_run_ts": row[9],
        "run_count": row[10],
        "last_result": row[11] or "",
        "created_at": row[12],
    }


def delete_task(task_id: int, db_path: str = DB_PATH) -> bool:
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def set_task_status(task_id: int, new_status: str, db_path: str = DB_PATH) -> bool:
    """Set task status: active, paused, completed, failed."""
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE scheduled_tasks SET status = ? WHERE id = ?", (new_status, task_id))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


async def execute_task_now(task: Dict[str, Any], application: Optional[Any] = None) -> Tuple[bool, str]:
    """Execute a single task and deliver output to Telegram."""
    tid = task["id"]
    name = task["name"]
    action = task["action_type"]
    payload = task["payload"]
    chat_id = task["chat_id"]
    t_start = time.time()

    logger.info(f"Executing scheduled task #{tid} '{name}' ({action})...")
    result_text = ""
    success = False

    try:
        if action == "reminder":
            result_text = payload
            success = True
            if application and chat_id:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🔔 <b>Rappel Programmé :</b> {name}\n\n"
                        f"{payload}"
                    ),
                    parse_mode="HTML",
                )

        elif action == "command":
            proc = await asyncio.create_subprocess_shell(
                payload,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKSPACE_DIR),
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=180.0)
            out_str = stdout_b.decode("utf-8", errors="replace").strip()
            err_str = stderr_b.decode("utf-8", errors="replace").strip()
            success = (proc.returncode == 0)
            result_text = out_str or err_str or "Commande exécutée sans sortie."

            if application and chat_id:
                formatted_out = result_text[:3500]
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚡ <b>Tâche Programmée — Commande Exécutée</b>\n"
                        f"• <b>Nom :</b> {name}\n"
                        f"• <b>Statut :</b> {'✅ Succès' if success else '❌ Échec'}\n\n"
                        f"<pre>{formatted_out}</pre>"
                    ),
                    parse_mode="HTML",
                )

        elif action == "prompt":
            from agent_runner import runner
            from config import load_settings
            app_settings = load_settings()

            scheduled_prompt = (
                f"[TÂCHE PROGRAMMÉE AUTONOME : '{name}']\n"
                f"Cette tâche s'exécute automatiquement selon sa planification.\n\n"
                f"Consigne :\n{payload}"
            )
            resp, ok = await runner.run_prompt_stream(
                prompt=scheduled_prompt,
                settings=app_settings,
            )
            success = ok
            result_text = resp

            if application and chat_id:
                from ui_helpers import md_to_html, sanitize_telegram_html, smart_split_html
                hdr = f"⏰ <b>Tâche Programmée Exécutée :</b> {name}\n\n"
                full_html = hdr + sanitize_telegram_html(md_to_html(resp))
                chunks = smart_split_html(full_html)
                for chunk in chunks:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="HTML",
                    )

    except Exception as e:
        logger.error(f"Error executing task #{tid}: {e}")
        success = False
        result_text = f"Erreur d'exécution: {e}"
        if application and chat_id:
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Erreur dans la tâche programmée '{name}' :</b> <code>{e}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    # Update database record
    now = time.time()
    conn = get_db()
    cur = conn.cursor()
    new_count = task["run_count"] + 1

    if task["task_type"] == "once":
        new_status = "completed" if success else "failed"
        cur.execute("""
            UPDATE scheduled_tasks
            SET status = ?, last_run_ts = ?, run_count = ?, last_result = ?
            WHERE id = ?
        """, (new_status, now, new_count, result_text[:500], tid))
    else:
        next_ts = compute_next_run(task["task_type"], task["schedule_expr"], now)
        cur.execute("""
            UPDATE scheduled_tasks
            SET last_run_ts = ?, next_run_ts = ?, run_count = ?, last_result = ?
            WHERE id = ?
        """, (now, next_ts or (now + 3600), new_count, result_text[:500], tid))

    conn.commit()
    conn.close()
    return success, result_text


async def scheduler_background_loop(application: Any):
    """Continuous background worker that checks and triggers due tasks."""
    logger.info("Autonomous Task Scheduler background loop started.")
    while True:
        try:
            await asyncio.sleep(15.0)
            now = time.time()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, task_type, schedule_expr, action_type, payload, chat_id, status, next_run_ts, last_run_ts, run_count, last_result, created_at
                FROM scheduled_tasks
                WHERE status = 'active' AND next_run_ts > 0 AND next_run_ts <= ?
            """, (now,))
            due_rows = cur.fetchall()
            conn.close()

            for row in due_rows:
                task = {
                    "id": row[0],
                    "name": row[1],
                    "task_type": row[2],
                    "schedule_expr": row[3],
                    "action_type": row[4],
                    "payload": row[5],
                    "chat_id": row[6],
                    "status": row[7],
                    "next_run_ts": row[8],
                    "last_run_ts": row[9],
                    "run_count": row[10],
                    "last_result": row[11],
                    "created_at": row[12],
                }
                asyncio.create_task(execute_task_now(task, application))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Scheduler loop non-fatal error: {e}")
            await asyncio.sleep(5.0)
