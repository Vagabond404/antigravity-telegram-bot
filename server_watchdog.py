"""
server_watchdog.py - Cross-Platform System Health Check & Service Monitor
Monitors System Services, Disk, RAM, CPU & Uptime on both Windows and Linux.
Defaults to English with full multi-language localization.
"""

import asyncio
import os
import time
import shutil
import platform
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
import psutil
from config import IS_WINDOWS

logger = logging.getLogger("server_watchdog")

SERVICES_CONFIG = {
    "antigravity-bot": {
        "name_en": "Telegram Bot Gateway",
        "name_fr": "Passerelle Bot Telegram",
        "type": "systemd",
        "service": "antigravity-bot",
        "restart_cmd": ["systemctl", "restart", "antigravity-bot"],
    }
}


async def _run_command(cmd: list) -> Tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )
    except Exception as e:
        return 1, "", str(e)


async def get_system_metrics(lang: str = "en") -> Dict[str, str]:
    is_fr = (lang == "fr")
    metrics = {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "uptime": "Unknown" if not is_fr else "Inconnu",
        "cpu": "0%",
        "ram": "Unknown" if not is_fr else "Inconnu",
        "disk": "Unknown" if not is_fr else "Inconnu",
    }

    try:
        up_secs = int(time.time() - psutil.boot_time())
        days = up_secs // 86400
        hours = (up_secs % 86400) // 3600
        mins = (up_secs % 3600) // 60
        day_suffix = "j" if is_fr else "d"
        if days > 0:
            metrics["uptime"] = f"{days}{day_suffix} {hours}h {mins}m"
        elif hours > 0:
            metrics["uptime"] = f"{hours}h {mins}m"
        else:
            metrics["uptime"] = f"{mins}m"
    except Exception:
        pass

    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        cores = psutil.cpu_count(logical=True) or 1
        core_lbl = "cœurs" if is_fr else "cores"
        metrics["cpu"] = f"{cpu_pct:.1f}% ({cores} {core_lbl})"
    except Exception:
        pass

    try:
        vm = psutil.virtual_memory()
        used_gb = (vm.total - vm.available) / (1024 ** 3)
        total_gb = vm.total / (1024 ** 3)
        unit = "Go" if is_fr else "GB"
        metrics["ram"] = f"{used_gb:.1f} / {total_gb:.1f} {unit} ({vm.percent:.0f}%)"
    except Exception:
        pass

    try:
        root_path = str(Path.home().anchor or "C:\\") if IS_WINDOWS else "/"
        du = psutil.disk_usage(root_path)
        free_gb = du.free / (1024 ** 3)
        total_gb = du.total / (1024 ** 3)
        if is_fr:
            metrics["disk"] = f"{free_gb:.1f} Go libres / {total_gb:.1f} Go ({du.percent:.0f}% occupé)"
        else:
            metrics["disk"] = f"{free_gb:.1f} GB free / {total_gb:.1f} GB ({du.percent:.0f}% used)"
    except Exception:
        pass

    return metrics


async def check_and_heal_services(auto_heal: bool = True, lang: str = "en") -> Tuple[Dict[str, Any], str, bool]:
    is_fr = (lang == "fr")
    results = {}
    has_healed_any = False

    has_systemctl = shutil.which("systemctl") is not None

    for key, conf in SERVICES_CONFIG.items():
        srv_name = conf["service"]
        display_name = conf["name_fr"] if is_fr else conf["name_en"]
        if key == "antigravity-bot":
            is_active = True
            details = "Actif (En ligne)" if is_fr else "Active (Online)"
        elif has_systemctl:
            rc, out, _ = await _run_command(["systemctl", "is-active", srv_name])
            is_active = (out.strip() == "active")
            if not is_active and auto_heal:
                await _run_command(conf["restart_cmd"])
                await asyncio.sleep(2)
                _, out, _ = await _run_command(["systemctl", "is-active", srv_name])
                is_active = (out.strip() == "active")
                if is_active:
                    has_healed_any = True
            if is_fr:
                details = "Actif" if is_active else "Arrêté"
            else:
                details = "Active" if is_active else "Stopped"
        else:
            is_active = True
            details = "Processus natif actif" if is_fr else "Native process active"

        results[key] = {
            "name": display_name,
            "status": "ONLINE" if is_active else "OFFLINE",
            "details": details,
        }

    metrics = await get_system_metrics(lang=lang)

    if is_fr:
        lines = [
            f"📊 <b>État du Système ({metrics['os']}) :</b>",
        ]
        for k, v in results.items():
            emoji = "✅" if v["status"] == "ONLINE" else "❌"
            lines.append(f"• <b>{v['name']} :</b> {emoji} {v['details']}")

        lines.append("")
        lines.append("⚙️ <b>Ressources Système :</b>")
        lines.append(f"• <b>CPU :</b> <code>{metrics['cpu']}</code>")
        lines.append(f"• <b>Mémoire RAM :</b> <code>{metrics['ram']}</code>")
        lines.append(f"• <b>Espace Disque :</b> <code>{metrics['disk']}</code>")
        lines.append(f"• <b>Uptime :</b> <code>{metrics['uptime']}</code>")
    else:
        lines = [
            f"📊 <b>System Status ({metrics['os']}):</b>",
        ]
        for k, v in results.items():
            emoji = "✅" if v["status"] == "ONLINE" else "❌"
            lines.append(f"• <b>{v['name']}:</b> {emoji} {v['details']}")

        lines.append("")
        lines.append("⚙️ <b>System Resources:</b>")
        lines.append(f"• <b>CPU:</b> <code>{metrics['cpu']}</code>")
        lines.append(f"• <b>RAM Memory:</b> <code>{metrics['ram']}</code>")
        lines.append(f"• <b>Disk Space:</b> <code>{metrics['disk']}</code>")
        lines.append(f"• <b>Uptime:</b> <code>{metrics['uptime']}</code>")

    report_html = "\n".join(lines)
    return results, report_html, has_healed_any


async def restart_service(service_name: str, lang: str = "en") -> Tuple[bool, str]:
    is_fr = (lang == "fr")
    if service_name in SERVICES_CONFIG:
        conf = SERVICES_CONFIG[service_name]
        d_name = conf["name_fr"] if is_fr else conf["name_en"]
        if shutil.which("systemctl"):
            rc, out, err = await _run_command(conf["restart_cmd"])
            if rc == 0:
                return True, f"{d_name} redémarré." if is_fr else f"{d_name} restarted successfully."
            else:
                return False, f"Erreur : {err}" if is_fr else f"Error: {err}"
        return False, "Systemd non disponible sur cet OS." if is_fr else "Systemd not available on this OS."
    return False, f"Service inconnu : {service_name}" if is_fr else f"Unknown service: {service_name}"
