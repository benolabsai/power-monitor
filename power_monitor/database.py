"""
Motherboard Super I/O & Sensor Pin Database
Provides out-of-the-box +12V rail mapping and heuristic detection so users
do not need custom /etc/sensors.d/ configuration files.
"""

import os
import glob
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
