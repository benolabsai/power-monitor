"""
Hardware Telemetry Engine
Reads real-time data from GPUs (NVIDIA, AMD, Intel), CPU Package Power (RAPL),
CPU thermals, and motherboard ATX power rails.
Optimized for minimal CPU and memory footprint: uses direct NVML C-FFI and sysfs reads.
"""

import os
import glob
import json
import time
import subprocess
import ctypes
from typing import Dict, List, Any, Optional, Tuple

from power_monitor.database import (
    get_dmi_info,
    lookup_motherboard_12v_profile,
    detect_heuristic_12v,
    load_calibration
)

class NvmlProber:
    """
    Ultra-lightweight direct C-FFI NVML GPU Telemetry.
    Eliminates process forks (nvidia-smi) for near-zero CPU and memory usage (~10 microseconds per query).
    """
    def __init__(self):
        self.available = False
        self.handles = []
        try:
            self.nvml = ctypes.CDLL("libnvidia-ml.so.1")
            if self.nvml.nvmlInit_v2() == 0:
                count = ctypes.c_uint()
                if self.nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) == 0:
                    for i in range(count.value):
                        h = ctypes.c_void_p()
                        if self.nvml.nvmlDeviceGetHandleByIndex_v2(i, ctypes.byref(h)) == 0:
                            name_buf = ctypes.create_string_buffer(64)
                            self.nvml.nvmlDeviceGetName(h, name_buf, 64)
                            name = name_buf.value.decode("utf-8", errors="ignore")
                            self.handles.append((i, h, name))
                    self.available = len(self.handles) > 0
        except Exception:
            self.available = False

    def probe(self) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        gpus = []
        for idx, h, name in self.handles:
            # Power Draw
            pwr = ctypes.c_uint()
            power_val = 0.0
            if self.nvml.nvmlDeviceGetPowerUsage(h, ctypes.byref(pwr)) == 0:
                power_val = pwr.value / 1000.0

            # Temperature
            temp = ctypes.c_uint()
            temp_val = 0.0
            if self.nvml.nvmlDeviceGetTemperature(h, 0, ctypes.byref(temp)) == 0:
                temp_val = float(temp.value)

            # GPU Utilization
            class NvmlUtilization(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]
            util = NvmlUtilization()
            util_val = 0.0
            if hasattr(self.nvml, "nvmlDeviceGetUtilizationRates") and self.nvml.nvmlDeviceGetUtilizationRates(h, ctypes.byref(util)) == 0:
                util_val = float(util.gpu)

            # VRAM
            class NvmlMemory(ctypes.Structure):
                _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]
            mem = NvmlMemory()
            mem_used_gb, mem_total_gb = 0.0, 0.0
            if hasattr(self.nvml, "nvmlDeviceGetMemoryInfo") and self.nvml.nvmlDeviceGetMemoryInfo(h, ctypes.byref(mem)) == 0:
                mem_used_gb = mem.used / (1024**3)
                mem_total_gb = mem.total / (1024**3)

            # Power Management Limit
            pwr_lim = ctypes.c_uint()
            pwr_lim_val = 0.0
            if hasattr(self.nvml, "nvmlDeviceGetPowerManagementLimit") and self.nvml.nvmlDeviceGetPowerManagementLimit(h, ctypes.byref(pwr_lim)) == 0:
                pwr_lim_val = pwr_lim.value / 1000.0

            # PCIe Link Generation and Width
            pcie_str = "PCIe"
            gen = ctypes.c_uint()
            width = ctypes.c_uint()
            if hasattr(self.nvml, "nvmlDeviceGetCurrPcieLinkGeneration") and hasattr(self.nvml, "nvmlDeviceGetCurrPcieLinkWidth"):
                if self.nvml.nvmlDeviceGetCurrPcieLinkGeneration(h, ctypes.byref(gen)) == 0 and self.nvml.nvmlDeviceGetCurrPcieLinkWidth(h, ctypes.byref(width)) == 0:
                    pcie_str = f"Gen{gen.value} x{width.value}"

            gpus.append({
                "vendor": "NVIDIA",
                "idx": idx,
                "name": name,
                "bus": f"GPU-{idx}",
                "pcie": pcie_str,
                "util": util_val,
                "mem_used": mem_used_gb,
                "mem_total": mem_total_gb,
                "power": power_val,
                "power_limit": pwr_lim_val,
                "temp": temp_val,
            })
        return gpus

_NVML_PROBER = NvmlProber()

def probe_gpus() -> List[Dict[str, Any]]:
    """Probes all system GPUs across NVIDIA, AMD Radeon, and Intel Arc."""
    gpus = []

    # 1. NVIDIA via direct C-FFI NVML (primary, ultra-fast) or nvidia-smi fallback
    if _NVML_PROBER.available:
        gpus.extend(_NVML_PROBER.probe())
    else:
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,pci.bus_id,pcie.link.gen.current,pcie.link.width.current,utilization.gpu,memory.used,memory.total,power.draw,power.limit,temperature.gpu",
                "--format=csv,noheader,nounits"
            ]
            res = subprocess.check_output(cmd, timeout=0.8).decode().strip().splitlines()
            for line in res:
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 11:
                    gpus.append({
                        "vendor": "NVIDIA",
                        "idx": int(parts[0]),
                        "name": parts[1],
                        "bus": parts[2],
                        "pcie": f"Gen{parts[3]} x{parts[4]}",
                        "util": float(parts[5]),
                        "mem_used": float(parts[6]) / 1024.0,
                        "mem_total": float(parts[7]) / 1024.0,
                        "power": float(parts[8]),
                        "power_limit": float(parts[9]),
                        "temp": float(parts[10]),
                    })
        except Exception:
            pass

    # 2. AMD & Intel via Linux DRM sysfs
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        dev = os.path.join(card, "device")
        driver_link = os.path.join(dev, "driver")
        if not os.path.exists(driver_link):
            continue
        driver = os.path.basename(os.readlink(driver_link))
        if driver not in ("amdgpu", "i915", "xe"):
            continue

        vendor = "AMD" if driver == "amdgpu" else "Intel"

        name = f"{vendor} GPU ({os.path.basename(card)})"
        product_file = os.path.join(dev, "product_name")
        if os.path.exists(product_file):
            try:
                with open(product_file) as f:
                    name = f.read().strip()
            except Exception:
                pass

        pwr, temp, pwr_lim = 0.0, 0.0, 0.0
        for h in glob.glob(os.path.join(dev, "hwmon", "hwmon*")):
            for pf in ("power1_average", "power1_input"):
                pfp = os.path.join(h, pf)
                if os.path.exists(pfp):
                    try:
                        pwr = int(open(pfp).read().strip()) / 1e6
                        break
                    except Exception:
                        pass
            for plf in ("power1_cap", "power1_crit"):
                plfp = os.path.join(h, plf)
                if os.path.exists(plfp):
                    try:
                        pwr_lim = int(open(plfp).read().strip()) / 1e6
                        break
                    except Exception:
                        pass
            temp_file = os.path.join(h, "temp1_input")
            if os.path.exists(temp_file):
                try:
                    temp = int(open(temp_file).read().strip()) / 1e3
                except Exception:
                    pass

        v_used, v_total = 0.0, 0.0
        v_used_file = os.path.join(dev, "mem_info_vram_used")
        v_tot_file = os.path.join(dev, "mem_info_vram_total")
        if os.path.exists(v_used_file) and os.path.exists(v_tot_file):
            try:
                v_used = int(open(v_used_file).read().strip()) / (1024**3)
                v_total = int(open(v_tot_file).read().strip()) / (1024**3)
            except Exception:
                pass

        util = 0.0
        util_file = os.path.join(dev, "gpu_busy_percent")
        if os.path.exists(util_file):
            try:
                util = float(open(util_file).read().strip())
            except Exception:
                pass

        pcie_str = "PCIe"
        w_file = os.path.join(dev, "current_link_width")
        s_file = os.path.join(dev, "current_link_speed")
        if os.path.exists(w_file) and os.path.exists(s_file):
            try:
                w = open(w_file).read().strip()
                s = open(s_file).read().strip()
                pcie_str = f"{s} {w}"
            except Exception:
                pass

        gpus.append({
            "vendor": vendor,
            "idx": len(gpus),
            "name": name,
            "bus": os.path.basename(os.path.realpath(dev)),
            "pcie": pcie_str,
            "util": util,
            "mem_used": v_used,
            "mem_total": v_total,
            "power": pwr,
            "power_limit": pwr_lim,
            "temp": temp,
        })

    return gpus

class CPUPowerReader:
    """
    Computes CPU Package Power in Watts using RAPL energy counters.
    Handles counter rollover and gracefully reports None if unprivileged.
    """
    def __init__(self):
        self.path = None
        self.last_energy = None
        self.last_time = None
        self.readable = False
        self._find_path()

    def _find_path(self):
        candidates = sorted(glob.glob("/sys/class/powercap/intel-rapl:*/energy_uj"))
        for p in candidates:
            try:
                with open(p) as f:
                    _ = f.read(1)
                self.path = p
                self.readable = True
                return
            except (PermissionError, IOError):
                self.path = p
                self.readable = False
                return

    def read_power(self) -> Optional[float]:
        if not self.path or not os.path.exists(self.path):
            return None

        now = time.time()
        try:
            with open(self.path) as f:
                energy = int(f.read().strip())
            self.readable = True
        except PermissionError:
            self.readable = False
            return None
        except Exception:
            return None

        if self.last_energy is None or self.last_time is None:
            self.last_energy = energy
            self.last_time = now
            return None

        dt = now - self.last_time
        de = energy - self.last_energy
        self.last_energy = energy
        self.last_time = now

        if dt <= 0.05:
            return None

        if de < 0:
            max_range_file = os.path.join(os.path.dirname(self.path), "max_energy_range_uj")
            max_val = (1 << 32)
            if os.path.exists(max_range_file):
                try:
                    max_val = int(open(max_range_file).read().strip())
                except Exception:
                    pass
            de += max_val

        power_w = de / (dt * 1e6)
        if 0.0 <= power_w <= 1000.0:
            return power_w
        return None

class TelemetryEngine:
    """
    Manages continuous polling and resolution of hardware sensors.
    Includes custom calibration factor support and fast direct sysfs reading.
    """

    def __init__(self, v12_multiplier: Optional[float] = None, v12_offset: Optional[float] = None):
        self.vendor, self.board_name = get_dmi_info()
        self.profile = lookup_motherboard_12v_profile(self.vendor, self.board_name)
        self.hwmon_chips = self._map_hwmon_chips()
        self.cpu_power_reader = CPUPowerReader()

        # Calibration resolution: explicit arg -> config file / env -> default 1.0
        cal_m, cal_o, cal_meta = load_calibration()
        self.v12_multiplier = v12_multiplier if v12_multiplier is not None else cal_m
        self.v12_offset = v12_offset if v12_offset is not None else cal_o
        self.cal_meta = cal_meta

    def _map_hwmon_chips(self) -> Dict[str, str]:
        """Maps chip names to their /sys/class/hwmon/hwmon* directory."""
        mapping = {}
        for p in glob.glob("/sys/class/hwmon/hwmon*"):
            name_file = os.path.join(p, "name")
            if os.path.exists(name_file):
                try:
                    with open(name_file) as f:
                        mapping[f.read().strip()] = p
                except Exception:
                    pass
        return mapping

    def read_12v_rail(self, sensors_data: Optional[Dict]) -> Tuple[Optional[float], str]:
        base_v = None
        base_src = "Unavailable"

        # 1. Driver-configured sensors data
        if sensors_data:
            for chip, sections in sensors_data.items():
                if not isinstance(sections, dict):
                    continue
                for label, vals in sections.items():
                    if not isinstance(vals, dict):
                        continue
                    clean_label = label.upper()
                    if "+12V" in clean_label or "12V" in clean_label:
                        for k, v in vals.items():
                            if "_input" in k and 9.0 <= v <= 15.0:
                                base_v = float(v)
                                base_src = "sensors configuration"
                                break
                    if base_v is not None:
                        break
                if base_v is not None:
                    break

        # 2. DMI profile fallback
        if base_v is None and self.profile:
            chip_key = self.profile["chip"]
            target_hwmon = None
            for name, path in self.hwmon_chips.items():
                if chip_key in name.lower():
                    target_hwmon = path
                    break

            if target_hwmon:
                pin_file = os.path.join(target_hwmon, self.profile["pin"])
                if os.path.exists(pin_file):
                    try:
                        with open(pin_file) as f:
                            raw_v = float(f.read().strip()) / 1000.0
                        calc_v = raw_v * self.profile["multiplier"]
                        if 9.0 <= calc_v <= 15.0:
                            base_v = calc_v
                            base_src = f"profile ({self.profile.get('notes', 'DMI')})"
                    except Exception:
                        pass

        # 3. Dynamic heuristic fallback
        if base_v is None:
            heuristic = detect_heuristic_12v()
            if heuristic:
                base_v = float(heuristic["detected_v"])
                base_src = heuristic["notes"]

        if base_v is None:
            return None, "Unavailable"

        # Apply calibration multiplier and offset if active
        cal_v = (base_v * self.v12_multiplier) + self.v12_offset
        if self.v12_multiplier != 1.0 or self.v12_offset != 0.0:
            cal_tag = f" [calibrated x{self.v12_multiplier:.4f}]"
        else:
            cal_tag = ""

        return cal_v, base_src + cal_tag

    def poll(self) -> Dict[str, Any]:
        """Collects one frame of system telemetry."""
        data: Dict[str, Any] = {
            "timestamp": time.time(),
            "gpus": probe_gpus(),
            "cpu_power": self.cpu_power_reader.read_power(),
            "cpu_power_readable": self.cpu_power_reader.readable,
        }

        sensors_json = None
        try:
            out = subprocess.check_output(["sensors", "-j"], timeout=0.8).decode()
            sensors_json = json.loads(out)
        except Exception:
            pass

        v12, v12_src = self.read_12v_rail(sensors_json)
        data["12v"] = v12
        data["12v_source"] = v12_src

        if sensors_json:
            for chip, sections in sensors_json.items():
                if not isinstance(sections, dict):
                    continue
                chip_lower = chip.lower()

                # CPU Temperature
                if any(k in chip_lower for k in ("k10temp", "coretemp", "zenpower", "cpu_thermal")):
                    for sec, vals in sections.items():
                        if isinstance(vals, dict):
                            for k, v in vals.items():
                                if "temp" in k and "_input" in k:
                                    data["cpu_temp"] = float(v)
                                    break

                # Motherboard Voltages, Temps, and Fans
                for label, vals in sections.items():
                    if not isinstance(vals, dict):
                        continue
                    clean_label = label.upper()

                    if "+3.3V" in clean_label or "3.3V" in clean_label or "3VCC" in clean_label:
                        for k, v in vals.items():
                            if "_input" in k and "3v3" not in data:
                                data["3v3"] = float(v)
                    elif "VCORE" in clean_label or label == "in0":
                        for k, v in vals.items():
                            if "_input" in k and "vcore" not in data:
                                data["vcore"] = float(v)
                    elif any(s in clean_label for s in ("MOTHERBOARD", "SYSTIN", "MB TEMP", "SYSTEM")):
                        for k, v in vals.items():
                            if "_input" in k and "mb_temp" not in data:
                                data["mb_temp"] = float(v)
                    elif any(f in clean_label for f in ("CPU FAN", "FAN1")):
                        for k, v in vals.items():
                            if "_input" in k and "cpu_fan" not in data:
                                data["cpu_fan"] = int(v)
                    elif any(f in clean_label for f in ("CHASSIS", "FAN3", "SYS_FAN")):
                        for k, v in vals.items():
                            if "_input" in k and "chassis_fan" not in data:
                                data["chassis_fan"] = int(v)

        return data
