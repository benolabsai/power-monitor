"""
System Log (Journald / Syslog) Telemetry Reporter.
Zero-noise when operating within normal bounds.
Immediately event-logs to systemd-journald and stdout the instant hardware
crosses specific thresholds (voltage sags, brownout collapses, thermal limits).
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
    """
    Event-driven logger that stays completely silent while hardware operates within normal bounds.
    The exact millisecond a metric crosses a safety threshold (e.g. +12V < 11.40V), an immediate event
    is published and flushed to the system journal so a hard crash/reboot never misses the cause.
    """
    def __init__(
        self,
        sag_warning_threshold: float = 11.40,
        sag_critical_threshold: float = 11.00,
        recovery_threshold: float = 11.50,
        rapid_drop_threshold: float = 0.35,
        heartbeat_interval: float = 300.0, # Slow 5-minute keepalive when healthy; set <= 0 to disable
    ):
        self.sag_warning_threshold = sag_warning_threshold
        self.sag_critical_threshold = sag_critical_threshold
        self.recovery_threshold = recovery_threshold
        self.rapid_drop_threshold = rapid_drop_threshold
        self.heartbeat_interval = heartbeat_interval

        self.last_heartbeat_time = time.time()
        self.prev_v12: Optional[float] = None
        self.rail_state: str = "HEALTHY" # "HEALTHY", "WARNING_LOW", "CRITICAL_LOW", "WARNING_HIGH"
        
        # Sag episode tracking
        self.in_sag_episode = False
        self.sag_start_time = 0.0
        self.sag_min_v12 = float("inf")
        self.last_logged_sag_min = float("inf")

        # Highest wattage tracking
        self.highest_wattage_seen = 0.0

    def log(self, priority: str, message: str):
        """Prints log line formatted with systemd-journal priority prefix and flushes immediately."""
        print(f"{priority}[power-monitor] {message}", file=sys.stdout)
        sys.stdout.flush()

    def inspect_frame(self, stats: Dict[str, Any]):
        """
        Inspects live frame.
        ZERO log output when operating within normal bounds.
        Immediate event logging on threshold crossings or rapid voltage drops.
        """
        now = time.time()
        v12 = stats.get("12v")
        gpus = stats.get("gpus", [])
        gpu_pwr_total = sum(g.get("power", 0.0) for g in gpus)
        cpu_pwr = stats.get("cpu_power")
        total_pwr = gpu_pwr_total + (cpu_pwr if cpu_pwr is not None else 0.0)
        
        gpu_detail = ", ".join([f"GPU{g['idx']}:{g['power']:.0f}W" for g in gpus]) or "no GPUs"

        if v12 is not None:
            # 1. Rapid Cliff Drop Detection (e.g. -0.4V drop between successive checks)
            if self.prev_v12 is not None:
                drop = self.prev_v12 - v12
                if drop >= self.rapid_drop_threshold and v12 < self.recovery_threshold:
                    self.log(
                        SD_WARNING,
                        f"RAPID SAG DETECTED: +12V plummeted from {self.prev_v12:.2f}V to {v12:.2f}V (-{drop:.2f}V plunge!) under {total_pwr:.1f}W load ({gpu_detail})"
                    )

            # 2. Threshold Crossing: Critical Undervoltage (< 11.00V)
            if v12 < self.sag_critical_threshold:
                if not self.in_sag_episode:
                    self.in_sag_episode = True
                    self.sag_start_time = now
                    self.sag_min_v12 = v12
                    self.last_logged_sag_min = v12
                else:
                    self.sag_min_v12 = min(self.sag_min_v12, v12)

                # Log immediately on state entry or if deepening by > 0.1V
                if self.rail_state != "CRITICAL_LOW" or (self.last_logged_sag_min - v12 >= 0.10):
                    self.rail_state = "CRITICAL_LOW"
                    self.last_logged_sag_min = v12
                    self.log(
                        SD_CRIT,
                        f"CRITICAL RAIL COLLAPSE: +12V collapsed to {v12:.2f}V! (<{self.sag_critical_threshold:.2f}V). Imminent brownout/UVP trip risk! (System Draw: {total_pwr:.1f}W, {gpu_detail})"
                    )

            # 3. Threshold Crossing: ATX Spec Sag (< 11.40V)
            elif v12 < self.sag_warning_threshold:
                if not self.in_sag_episode:
                    self.in_sag_episode = True
                    self.sag_start_time = now
                    self.sag_min_v12 = v12
                    self.last_logged_sag_min = v12
                else:
                    self.sag_min_v12 = min(self.sag_min_v12, v12)

                # Log immediately on state entry or if deepening by > 0.1V
                if self.rail_state != "WARNING_LOW" or (self.last_logged_sag_min - v12 >= 0.10):
                    self.rail_state = "WARNING_LOW"
                    self.last_logged_sag_min = v12
                    self.log(
                        SD_WARNING,
                        f"ATX RAIL SAG: +12V dipped below spec to {v12:.2f}V (<{self.sag_warning_threshold:.2f}V). Total Draw: {total_pwr:.1f}W ({gpu_detail})"
                    )

            # 4. Overvoltage (> 12.60V)
            elif v12 > 12.60:
                if self.rail_state != "WARNING_HIGH":
                    self.rail_state = "WARNING_HIGH"
                    self.log(
                        SD_WARNING,
                        f"ATX OVERVOLTAGE: +12V rail exceeded spec to {v12:.2f}V (>12.60V max). Total Draw: {total_pwr:.1f}W"
                    )

            # 5. Recovery Event (voltage rises back above recovery threshold, e.g. 11.50V)
            elif self.in_sag_episode and v12 >= self.recovery_threshold:
                duration_ms = (now - self.sag_start_time) * 1000.0
                lowest_v = self.sag_min_v12
                self.log(
                    SD_NOTICE,
                    f"RAIL RECOVERED: +12V recovered to {v12:.2f}V (sag episode lasted {duration_ms:.0f}ms, lowest dip reached was {lowest_v:.2f}V). System Draw: {total_pwr:.1f}W"
                )
                self.in_sag_episode = False
                self.sag_min_v12 = float("inf")
                self.last_logged_sag_min = float("inf")
                self.rail_state = "HEALTHY"

            else:
                self.rail_state = "HEALTHY"

            self.prev_v12 = v12

        # 6. Thermal Critical Thresholds (Only when overheating)
        for g in gpus:
            if g.get("temp", 0) >= 88.0:
                self.log(
                    SD_WARNING,
                    f"Thermal Warning: GPU {g.get('idx')} ({g.get('name')}) reached {g.get('temp'):.0f}°C under {g.get('power', 0):.1f}W draw."
                )

        cpu_temp = stats.get("cpu_temp")
        if cpu_temp is not None and cpu_temp >= 90.0:
            self.log(
                SD_WARNING,
                f"Thermal Warning: CPU reached {cpu_temp:.1f}°C."
            )

        # 7. Slow Keepalive Heartbeat (Only every 5 min if healthy, or user configured)
        if self.heartbeat_interval > 0 and (now - self.last_heartbeat_time) >= self.heartbeat_interval:
            self.last_heartbeat_time = now
            v12_str = f"{v12:.2f}V" if v12 is not None else "--"
            cpu_p_str = f"({cpu_pwr:.0f}W)" if cpu_pwr is not None else ""
            cpu_s = f"{cpu_temp:.0f}°C{cpu_p_str}" if cpu_temp is not None else "--"
            self.log(
                SD_INFO,
                f"Keepalive: +12V={v12_str} (in bounds) | Total={total_pwr:.1f}W | CPU={cpu_s} | {gpu_detail}"
            )
