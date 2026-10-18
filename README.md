# Hardware Power & Voltage Monitor (`power-monitor`)

A lightweight, native GTK3 hardware telemetry monitor and desktop top-panel indicator for Linux PC builders, overclockers, and multi-GPU AI/rendering workstations.

![Power Monitor Icon](data/icons/power-monitor.svg)

---

## Key Features

1. **Top-Panel Live Indicator (Ayatana AppIndicator)**
   - Natively integrates into the Ubuntu top bar (e.g. `⚡ 12.00V | 38W`).
   - Quick dropdown menu with rail health, GPU load, thermals, session recording, and one-click access to the dashboard.
   - Built to run seamlessly in the background without needing third-party GNOME JavaScript extensions.

2. **Dual Anti-Aliased Real-Time Vector Charts (Cairo)**
   - **+12V Main ATX Power Rail Stability**: Tracks continuous PSU rail sag against the official ATX specification (11.40V – 12.60V) with warning/critical margins.
   - **Multi-Line Real-Time Wattage**: Visualizes each discrete GPU's power curve alongside total combined wattage.
   - **Horizontal-Only Resizing**: Charts stretch horizontally to fit any multi-monitor or ultra-wide display while locking vertical height to keep system metrics visible.

3. **Universal Motherboard & GPU Auto-Detection**
   - **Zero-Config DMI Database**: Built-in resistor divider table for ASUS, MSI, and Gigabyte motherboards (eliminates manual `/etc/sensors.d/` editing).
   - **Heuristic 12V Scanner**: Automatically identifies Super I/O pins (Nuvoton NCT67xx, ITE IT86xx/IT87xx) reading standard analog divider voltages.
   - **Multi-Vendor GPU Telemetry**: Supports NVIDIA (`nvidia-smi` / NVML), AMD Radeon (`amdgpu`), and Intel Arc (`i915` / `xe`).

4. **Crash-Resilient Session Recording**
   - On-demand CSV flight recorder with zero-loss flushing (`flush()`).
   - Diagnostic post-mortem analysis: If the PC experiences a brownout or hard crash during a heavy render or AI run, the log records the exact millisecond-level voltage drop leading right up to the crash.

---

## Quick Start

### Run from Source
```bash
# Launch GUI and top-panel indicator
make run

# Or launch minimized as a top-panel indicator only
make indicator

# Or print an instantaneous terminal telemetry snapshot
make status
```

---

## Building Debian Packages & PPA Distribution

### Build Local `.deb` Package
```bash
make deb
# Installs cleanly with dpkg:
sudo dpkg -i ../power-monitor_1.0.0-1_all.deb
```

### Publishing to an Ubuntu Launchpad PPA
1. Create a PPA on [Launchpad.net](https://launchpad.net) (e.g., `ppa:yourname/power-monitor`).
2. Build the signed source package:
   ```bash
   make ppa
   ```
3. Upload to Launchpad via `dput`:
   ```bash
   dput ppa:yourname/power-monitor ../power-monitor_1.0.0-1_source.changes
   ```
4. End users can then install it with standard APT commands:
   ```bash
   sudo add-apt-repository ppa:yourname/power-monitor
   sudo apt update
   sudo apt install power-monitor
   ```

---

## CLI Options

```text
usage: power-monitor [-h] [-v] [--no-gui] [--log-csv [PATH]] [--status] [--debug]

options:
  -h, --help        show this help message and exit
  -v, --version     show program's version number and exit
  --no-gui          start minimized as a top-panel indicator only
  --log-csv [PATH]  record telemetry samples to CSV
  --status          print instantaneous hardware snapshot to console and exit
  --debug           enable verbose debug logging
```

---

## License
GNU General Public License v3.0 or later (GPL-3.0-or-later).
