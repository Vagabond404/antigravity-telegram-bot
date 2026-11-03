#!/usr/bin/env python3
"""
tasks.py - Scheduled Tasks & Autonomous Background Automation CLI
CLI interface for Antigravity Telegram Agent v5.1
Allows both the AI agent and the human user to create and manage scheduled tasks.
"""

import sys
import argparse
import json
import time
from datetime import datetime

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from scheduler_manager import (
    add_task, list_tasks, get_task, delete_task,
    set_task_status, parse_schedule_expression
)
from auth_manager import auth_mgr

def main():
    parser = argparse.ArgumentParser(description="Antigravity Scheduled Tasks & Automation CLI")
    subparsers = parser.add_subparsers(dest="command")

    # add
    p_add = subparsers.add_parser("add", help="Schedule a new task or automation")
    p_add.add_argument("payload", help="Prompt to execute, shell command, or reminder message")
    p_add.add_argument("--when", "-w", required=True, help="Schedule expr (e.g. 'in 30m', '18:00', 'every 2h', '0 9 * * *')")
    p_add.add_argument("--name", "-n", default="", help="Short descriptive name for the task")
    p_add.add_argument("--type", "-t", choices=["prompt", "command", "reminder"], default="prompt", help="Action type (default: prompt)")
    p_add.add_argument("--chat", "-c", type=int, default=0, help="Target Telegram Chat ID (defaults to primary admin)")

    # list
    p_list = subparsers.add_parser("list", help="List scheduled tasks")
    p_list.add_argument("--status", choices=["active", "paused", "completed", "failed"], default=None)
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # remove / delete
    p_del = subparsers.add_parser("remove", help="Delete a scheduled task by ID")
    p_del.add_argument("id", type=int, help="Task ID")

    # pause
    p_pause = subparsers.add_parser("pause", help="Pause an active task")
    p_pause.add_argument("id", type=int, help="Task ID")

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume a paused task")
    p_resume.add_argument("id", type=int, help="Task ID")

    # info
    p_info = subparsers.add_parser("info", help="Get details of a task")
    p_info.add_argument("id", type=int, help="Task ID")

    args = parser.parse_args()

    if args.command == "add":
        chat_id = args.chat
        if not chat_id:
            chat_id = auth_mgr.get_primary_admin_id() or 0

        name = args.name or f"Task_{int(time.time())}"
        tid = add_task(
            name=name,
            schedule_expr=args.when,
            payload=args.payload,
            action_type=args.type,
            chat_id=chat_id,
        )
        task = get_task(tid)
        if task:
            next_str = datetime.fromtimestamp(task['next_run_ts']).strftime("%Y-%m-%d %H:%M:%S")
            print(f"✅ Tâche #{tid} programmée avec succès : '{name}'")
            print(f"  • Type : {task['task_type']} ({args.type})")
            print(f"  • Planification : {args.when} ➔ Prochaine exécution : {next_str}")
            print(f"  • Destinataire : Chat Telegram {chat_id}")
        else:
            print(f"❌ Erreur lors de la création de la tâche.")

    elif args.command == "list":
        tasks = list_tasks(status=args.status)
        if args.json:
            print(json.dumps(tasks, indent=2, ensure_ascii=False))
            return

        print(f"📋 {len(tasks)} tâche(s) programmée(s) :")
        if not tasks:
            print("  (Aucune tâche programmée)")
            return

        for t in tasks:
            status_emoji = {"active": "🟢", "paused": "⏸️", "completed": "✅", "failed": "❌"}.get(t["status"], "🔹")
            next_str = datetime.fromtimestamp(t["next_run_ts"]).strftime("%d/%m %H:%M") if t["next_run_ts"] > 0 else "N/A"
            print(f"  • [#{t['id']}] {status_emoji} {t['name']} ({t['action_type']}) | Planif: {t['schedule_expr']} | Prochain: {next_str} | Runs: {t['run_count']}")

    elif args.command == "remove":
        ok = delete_task(args.id)
        print(f"🗑️ Tâche #{args.id} supprimée." if ok else f"❌ Tâche #{args.id} introuvable.")

    elif args.command == "pause":
        ok = set_task_status(args.id, "paused")
        print(f"⏸️ Tâche #{args.id} suspendue." if ok else f"❌ Tâche #{args.id} introuvable.")

    elif args.command == "resume":
        ok = set_task_status(args.id, "active")
        print(f"▶️ Tâche #{args.id} réactivée." if ok else f"❌ Tâche #{args.id} introuvable.")

    elif args.command == "info":
        task = get_task(args.id)
        if task:
            print(json.dumps(task, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Tâche #{args.id} introuvable.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
