"""
Motherboard Super I/O & Sensor Pin Database
Provides out-of-the-box +12V rail mapping and heuristic detection so users
do not need custom /etc/sensors.d/ configuration files.
Includes persistent per-board multimeter calibration loading and saving.
"""

import os
import glob
import json
import time
from typing import Optional, Dict, Any, Tuple

# Database of verified motherboard DMI profiles for the ATX +12V rail
# Format: (vendor_keyword, model_keyword): {"chip": str, "pin": str, "multiplier": float}
MOTHERBOARD_PROFILES = {
    # ASUS AMD AM4 / AM5 (NCT6798D / NCT6796D / NCT6799D)
    ("asus", "prime x570-pro"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "prime x570-p"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "tuf gaming x570-plus"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "tuf gaming x570-pro"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "rog strix b550-f"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "rog strix b550-e"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "rog strix x570-e"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "rog crosshair viii"): {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "tuf gaming b650"): {"chip": "nct6799", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},
    ("asus", "rog strix x670e"): {"chip": "nct6799", "pin": "in5_input", "multiplier": 14.0, "notes": "ASUS 1:14 divider"},

    # MSI AMD & Intel (NCT6795 / NCT6797 / NCT6687)
    ("micro-star", "b450 tomahawk"): {"chip": "nct6797", "pin": "in5_input", "multiplier": 12.0, "notes": "MSI 1:12 divider"},
    ("micro-star", "mag b550 tomahawk"): {"chip": "nct6687", "pin": "in4_input", "multiplier": 12.0, "notes": "MSI 1:12 divider"},
    ("micro-star", "mpg x570"): {"chip": "nct6797", "pin": "in5_input", "multiplier": 12.0, "notes": "MSI 1:12 divider"},
    ("micro-star", "pro z690"): {"chip": "nct6687", "pin": "in4_input", "multiplier": 12.0, "notes": "MSI 1:12 divider"},

    # Gigabyte (ITE IT8686 / IT8688 / IT8792)
    ("gigabyte", "x570 aorus"): {"chip": "it8688", "pin": "in2_input", "multiplier": 6.0, "notes": "Gigabyte 1:6 divider"},
    ("gigabyte", "b550 aorus"): {"chip": "it8686", "pin": "in2_input", "multiplier": 6.0, "notes": "Gigabyte 1:6 divider"},
}

KNOWN_SUPERIO_CHIPS = (
    "nct6775", "nct6776", "nct6779", "nct6791", "nct6792",
    "nct6793", "nct6795", "nct6796", "nct6797", "nct6798", "nct6799",
    "nct6683", "nct6686", "nct6687",
    "it8620", "it8628", "it8686", "it8688", "it8728", "it8792", "it8795",
    "w83627", "w83667",
)

def get_dmi_info() -> Tuple[str, str]:
    """Reads motherboard vendor and product name from sysfs DMI."""
    vendor = "Unknown"
    product = "Unknown"
    try:
        if os.path.exists("/sys/class/dmi/id/board_vendor"):
            with open("/sys/class/dmi/id/board_vendor") as f:
                vendor = f.read().strip()
    except Exception:
        pass

    try:
        if os.path.exists("/sys/class/dmi/id/board_name"):
            with open("/sys/class/dmi/id/board_name") as f:
                product = f.read().strip()
    except Exception:
        pass

    return vendor, product

def lookup_motherboard_12v_profile(vendor: str, product: str) -> Optional[Dict[str, Any]]:
    """Checks if the current motherboard matches a known +12V rail configuration."""
    v_norm = vendor.strip().lower()
    p_norm = product.strip().lower()

    for (db_vendor, db_product), conf in MOTHERBOARD_PROFILES.items():
        if db_vendor in v_norm and db_product in p_norm:
            return conf

    # Generic vendor match for NCT6798 on ASUS
    if "asus" in v_norm:
        return {"chip": "nct6798", "pin": "in5_input", "multiplier": 14.0, "notes": "Generic ASUS NCT6798 profile"}

    return None

def detect_heuristic_12v() -> Optional[Dict[str, Any]]:
    """
    Automated Heuristic Fallback:
    Scans hwmon Super I/O pins for raw analog voltages in the typical divider ranges
    (e.g., 0.70V - 1.05V for 1:12-1:15 dividers, or 1.8V - 2.1V for 1:6 dividers)
    and calculates the multiplier that aligns with ATX 12V specification (11.4V - 12.6V).
    """
    standard_multipliers = [14.0, 12.0, 6.0, 10.0, 15.0]

    for hwmon_dir in glob.glob("/sys/class/hwmon/hwmon*"):
        name_file = os.path.join(hwmon_dir, "name")
        if not os.path.exists(name_file):
            continue
        try:
            with open(name_file) as f:
                chip_name = f.read().strip().lower()
        except Exception:
            continue

        if not any(k in chip_name for k in KNOWN_SUPERIO_CHIPS):
            continue

        # Inspect all voltage input files: in0_input to in15_input
        for pin_file in sorted(glob.glob(os.path.join(hwmon_dir, "in*_input"))):
            pin_name = os.path.basename(pin_file)
            try:
                with open(pin_file) as f:
                    raw_mv = float(f.read().strip())
                raw_v = raw_mv / 1000.0
            except Exception:
                continue

            for mult in standard_multipliers:
                calc_v = raw_v * mult
                if 11.60 <= calc_v <= 12.40:
                    return {
                        "chip": chip_name,
                        "hwmon_path": hwmon_dir,
                        "pin": pin_name,
                        "multiplier": mult,
                        "detected_v": calc_v,
                        "notes": f"Auto-detected via {chip_name} {pin_name} (raw {raw_v:.3f}V * {mult}x)"
                    }

    return None

def get_calibration_path() -> str:
    """Returns system or user-specific path to calibration configuration file."""
    sys_dir = "/etc/power-monitor"
    if os.path.exists(sys_dir) and os.access(sys_dir, os.W_OK):
        return os.path.join(sys_dir, "calibration.json")
    user_dir = os.path.expanduser("~/.config/power-monitor")
    return os.path.join(user_dir, "calibration.json")

def load_calibration() -> Tuple[float, float, Optional[Dict[str, Any]]]:
    """
    Loads custom +12V rail calibration multiplier and offset.
    Resolution priority:
      1. Environment variables (POWER_MONITOR_V12_MULTIPLIER, POWER_MONITOR_V12_OFFSET)
      2. /etc/power-monitor/calibration.json
      3. ~/.config/power-monitor/calibration.json
    Returns (multiplier, offset, metadata_dict).
    """
    # 1. Environment variables
    env_mult = os.environ.get("POWER_MONITOR_V12_MULTIPLIER")
    env_off = os.environ.get("POWER_MONITOR_V12_OFFSET")
    if env_mult is not None:
        try:
            m = float(env_mult)
            o = float(env_off) if env_off else 0.0
            return m, o, {"source": "environment_variable"}
        except ValueError:
            pass

    # 2. Config files
    candidates = [
        "/etc/power-monitor/calibration.json",
        os.path.expanduser("~/.config/power-monitor/calibration.json")
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c) as f:
                    data = json.load(f)
                m = float(data.get("v12_multiplier", 1.0))
                o = float(data.get("v12_offset", 0.0))
                return m, o, data
            except Exception:
                pass

    return 1.0, 0.0, None

def save_calibration(target_volts: float, raw_volts: float, sensor_info: str) -> Tuple[float, str]:
    """
    Computes and persists the calibration multiplier based on a physical multimeter reading.
    Formula: multiplier = target_volts / raw_volts
    """
    if raw_volts <= 0.0:
        multiplier = 1.0
    else:
        multiplier = target_volts / raw_volts

    target_path = get_calibration_path()
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    vendor, board = get_dmi_info()
    data = {
        "v12_multiplier": round(multiplier, 6),
        "v12_offset": 0.0,
        "calibrated_against_volts": round(target_volts, 3),
        "measured_base_volts": round(raw_volts, 3),
        "motherboard": f"{vendor} {board}",
        "sensor_source": sensor_info,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(target_path, "w") as f:
        json.dump(data, f, indent=2)

    return multiplier, target_path
