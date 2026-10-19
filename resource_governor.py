"""
resource_governor.py - Hardware Profiling, Dynamic Throttling & Anti-Crash Governor
Protects low-resource devices (Armbian SBCs, TV Boxes, Raspberry Pis, low-RAM VMs)
from CPU starvation, Out-Of-Memory (OOM) crashes, and sluggishness.
"""

import os
import gc
import sys
import time
import logging
import platform
import asyncio
from typing import Dict, Any, Tuple

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("resource_governor")

LOW_MEMORY_THRESHOLD_MB = 180.0
HIGH_CPU_THRESHOLD_PCT = 90.0


class ResourceGovernor:
    """
    Monitors host hardware metrics and adapts bot execution limits
    to prevent crashes and freezes on resource-constrained devices.
    """

    def __init__(self):
        self.is_linux = sys.platform.startswith("linux")
        self.total_ram_mb = 0.0
        self.cpu_count = os.cpu_count() or 1
        self.low_resource_mode = False
        self.turn_in_progress = False
        self._detect_hardware_profile()
        self._apply_gentle_priority()

    def _detect_hardware_profile(self) -> None:
        if psutil:
            try:
                mem = psutil.virtual_memory()
                self.total_ram_mb = mem.total / (1024 * 1024)
            except Exception as e:
                logger.debug(f"Could not read virtual_memory: {e}")
                self.total_ram_mb = 2048.0
        else:
            self.total_ram_mb = 2048.0

        # Devices with <= 2.5 GB RAM or single/dual-core ARM CPUs are classified as low-resource
        is_arm = ("arm" in platform.machine().lower() or "aarch" in platform.machine().lower())
        if self.total_ram_mb <= 2560.0 or (is_arm and self.total_ram_mb <= 4096.0):
            self.low_resource_mode = True
            logger.info(
                f"Low-resource hardware profile activated (RAM: {self.total_ram_mb:.0f}MB, "
                f"CPUs: {self.cpu_count}, Arch: {platform.machine()}). Protective throttling enabled."
            )
        else:
            logger.info(
                f"Standard hardware profile detected (RAM: {self.total_ram_mb:.0f}MB, "
                f"CPUs: {self.cpu_count})."
            )

    def _apply_gentle_priority(self) -> None:
        """Lower CPU scheduling priority slightly on Unix to keep the kernel and network responsive."""
        if not self.is_linux:
            return
        try:
            if hasattr(os, "nice"):
                current_nice = os.nice(0)
                if current_nice < 5:
                    os.nice(5)
                    logger.debug(f"Adjusted process nice value to +5 for stability.")
        except Exception as e:
            logger.debug(f"Could not adjust process nice: {e}")

    def is_stressed(self) -> Tuple[bool, str]:
        """Check if system is under severe memory or CPU pressure."""
        if not psutil:
            return False, ""

        try:
            mem = psutil.virtual_memory()
            avail_mb = mem.available / (1024 * 1024)
            if avail_mb < LOW_MEMORY_THRESHOLD_MB:
                return True, f"Low available RAM ({avail_mb:.1f} MB remaining)"

            cpu_pct = psutil.cpu_percent(interval=0.1)
            if cpu_pct > HIGH_CPU_THRESHOLD_PCT and self.low_resource_mode:
                return True, f"High CPU utilization ({cpu_pct:.1f}%)"
        except Exception:
            pass

        return False, ""

    def start_turn(self) -> None:
        """Mark start of a user turn to throttle background polling."""
        self.turn_in_progress = True

    def end_turn(self) -> None:
        """Mark end of a user turn and run garbage collection."""
        self.turn_in_progress = False
        self.cleanup_memory()

    def should_delay_background_task(self) -> bool:
        """Return True if background workers should yield execution during an active turn or high load."""
        if self.turn_in_progress and self.low_resource_mode:
            return True
        stressed, _ = self.is_stressed()
        return stressed

    def cleanup_memory(self) -> None:
        """Perform garbage collection to release transient memory back to OS."""
        try:
            gc.collect()
        except Exception:
            pass

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Return structured hardware and throttling metrics."""
        cpu_pct = 0.0
        used_ram_mb = 0.0
        total_ram_mb = self.total_ram_mb
        avail_ram_mb = 0.0
        load_avg = ""

        if psutil:
            try:
                cpu_pct = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                used_ram_mb = (mem.total - mem.available) / (1024 * 1024)
                avail_ram_mb = mem.available / (1024 * 1024)
            except Exception:
                pass

        if hasattr(os, "getloadavg"):
            try:
                l1, l5, l15 = os.getloadavg()
                load_avg = f"{l1:.2f}, {l5:.2f}, {l15:.2f}"
            except Exception:
                pass

        status_badge = "🟢 Optimal"
        stressed, reason = self.is_stressed()
        if stressed:
            status_badge = f"🟡 Throttled ({reason})"
        elif self.low_resource_mode:
            status_badge = "🟢 Low-Resource Guard Active"

        return {
            "cpu_percent": cpu_pct,
            "cpu_count": self.cpu_count,
            "used_ram_mb": used_ram_mb,
            "total_ram_mb": total_ram_mb,
            "avail_ram_mb": avail_ram_mb,
            "load_avg": load_avg,
            "low_resource_mode": self.low_resource_mode,
            "status_badge": status_badge,
        }


# Global Governor Singleton
governor = ResourceGovernor()
