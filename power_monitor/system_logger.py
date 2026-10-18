"""
System Log (Journald / Syslog) Telemetry Reporter.
Logs power anomalies, voltage sags, and heartbeats directly into the Linux system journal.
Integrates natively with:
  journalctl -u power-monitor
  journalctl -p warning -u power-monitor
  journalctl -u power-monitor -b -1  (post-mortem previous boot analysis)
"""

import sys
import time
from typing import Dict, Any, Optional

# Standard systemd-journal priority prefixes
SD_EMERG   = "<0>"
SD_ALERT   = "<1>"
SD_CRIT    = "<2>"
SD_ERR     = "<3>"
SD_WARNING = "<4>"
SD_NOTICE  = "<5>"
SD_INFO    = "<6>"
SD_DEBUG   = "<7>"

class SystemJournalLogger:
    def __init__(self, heartbeat_interval: float = 30.0):
        self.heartbeat_interval = heartbeat_interval
        self.last_heartbeat_time = 0.0
        self.last_reported_v12: Optional[float] = None
        self.last_rail_state: str = "HEALTHY"
        self.highest_wattage_seen = 0.0

    def log(self, priority: str, message: str):
        """Prints log line formatted with systemd-journal priority prefix and flushes immediately."""
        print(f"{priority}[power-monitor] {message}", file=sys.stdout)
        sys.stdout.flush()

    def inspect_frame(self, stats: Dict[str, Any]):
        """
        Analyzes live telemetry against ATX hardware specifications.
        Immediately emits system journal events on anomalies, rail sags, and high load steps,
        plus a periodic summary heartbeat.
        """
        now = time.time()
        v12 = stats.get("12v")
        gpus = stats.get("gpus", [])
        gpu_pwr_total = sum(g.get("power", 0.0) for g in gpus)
        cpu_pwr = stats.get("cpu_power")
        total_pwr = gpu_pwr_total + (cpu_pwr if cpu_pwr is not None else 0.0)
        cpu_temp = stats.get("cpu_temp")

        # 1. ATX +12V Rail Stability Analysis (11.40V - 12.60V Margin)
        if v12 is not None:
            if v12 < 11.00:
                current_state = "CRITICAL_LOW"
                if self.last_rail_state != current_state:
                    self.log(
                        SD_CRIT,
                        f"CRITICAL RAIL UNDERVOLTAGE: +12V rail collapsed to {v12:.2f}V! (System load: {total_pwr:.1f}W). Imminent brownout/reboot risk."
                    )
            elif v12 < 11.40:
                current_state = "WARNING_LOW"
                if self.last_rail_state != current_state:
                    self.log(
                        SD_WARNING,
                        f"ATX 12V RAIL SAG: Voltage dipped below spec margin to {v12:.2f}V (<11.40V min). Total Draw: {total_pwr:.1f}W."
                    )
            elif v12 > 12.60:
                current_state = "WARNING_HIGH"
                if self.last_rail_state != current_state:
                    self.log(
                        SD_WARNING,
                        f"ATX 12V OVERVOLTAGE: Rail exceeded spec margin to {v12:.2f}V (>12.60V max)."
                    )
            else:
                current_state = "HEALTHY"
                if self.last_rail_state != "HEALTHY":
                    self.log(
                        SD_NOTICE,
                        f"ATX +12V Rail recovered to normal operating margin ({v12:.2f}V)."
                    )

            self.last_rail_state = current_state

        # 2. Significant Wattage Step / Peak Detection
        if total_pwr > (self.highest_wattage_seen + 50.0):
            self.highest_wattage_seen = total_pwr
            v_str = f"{v12:.2f}V" if v12 is not None else "--"
            breakdown = f"GPUs: {gpu_pwr_total:.1f}W" + (f", CPU: {cpu_pwr:.1f}W" if cpu_pwr is not None else "")
            self.log(
                SD_INFO,
                f"New peak system draw: {total_pwr:.1f}W ({breakdown}, 12V Rail: {v_str})"
            )

        # 3. GPU & CPU Thermal Warnings
        for g in gpus:
            if g.get("temp", 0) >= 88.0:
                self.log(
                    SD_WARNING,
                    f"Thermal Warning: GPU {g.get('idx')} ({g.get('name')}) reached {g.get('temp'):.0f}°C under {g.get('power', 0):.1f}W draw."
                )

        if cpu_temp is not None and cpu_temp >= 90.0:
            self.log(
                SD_WARNING,
                f"Thermal Warning: CPU reached {cpu_temp:.1f}°C."
            )

        # 4. Periodic Heartbeat Summary (every 30s)
        if (now - self.last_heartbeat_time) >= self.heartbeat_interval:
            self.last_heartbeat_time = now
            v12_str = f"{v12:.2f}V" if v12 is not None else "--"
            cpu_p_str = f"({cpu_pwr:.0f}W)" if cpu_pwr is not None else ""
            cpu_s = f"{cpu_temp:.0f}°C{cpu_p_str}" if cpu_temp is not None else "--"
            gpu_summary = ", ".join([f"GPU{g['idx']}:{g['power']:.0f}W({g['temp']:.0f}°C)" for g in gpus]) or "No active discrete GPUs"
            self.log(
                SD_INFO,
                f"Status: +12V={v12_str} | Total={total_pwr:.1f}W | CPU={cpu_s} | {gpu_summary}"
            )
