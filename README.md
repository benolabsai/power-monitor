# Hardware Power & Voltage Monitor (`power-monitor`)

[![Release](https://img.shields.io/github/v/release/benolabsai/power-monitor?color=blue&logo=github)](https://github.com/benolabsai/power-monitor/releases)
[![Ubuntu PPA](https://img.shields.io/badge/Ubuntu%20PPA-ppa%3Abenolabs%2Fppa-orange?logo=ubuntu)](https://launchpad.net/~benolabs/+archive/ubuntu/ppa)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

A lightweight, native GTK3 telemetry monitor and top-panel indicator designed for Linux PC builders, overclockers, AI workstation engineers, and multi-GPU render rigs.

![Power Monitor Icon](data/icons/power-monitor.svg)

---

## ⚡ Installation

### Option 1: Official Ubuntu PPA (Recommended)

Keep `power-monitor` continuously up to date via standard system updates:

```bash
# Add the official Beno Labs PPA
sudo add-apt-repository ppa:benolabs/ppa
sudo apt update

# Install Power Monitor
sudo apt install power-monitor
```

### Option 2: Direct `.deb` Download

Download the latest prebuilt `.deb` package directly from [GitHub Releases](https://github.com/benolabsai/power-monitor/releases):

```bash
# Download and install the package
sudo dpkg -i power-monitor_1.0.1_all.deb
sudo apt install -f  # Resolves any missing system libraries
```

### Option 3: Run from Source

For local development or hacking on the telemetry engine:

```bash
git clone https://github.com/benolabsai/power-monitor.git
cd power-monitor

# Install runtime dependencies on Ubuntu / Debian:
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 python3-cairo lm-sensors

# Launch full GUI dashboard and top-panel indicator:
make run

# Or launch minimized as a top-panel indicator only:
make indicator

# Or print an instantaneous hardware snapshot to terminal:
make status
```

---

## ✨ Key Features

### 1. Top-Panel Live Indicator (Ayatana AppIndicator)
* Displays real-time telemetry right in the Ubuntu / GNOME top bar (e.g. `⚡ 11.98V | 83W`).
* Clickable dropdown menu showing instantaneous +12V rail voltage, combined GPU power, CPU package power, and thermals.
* One-click session recording toggle and dashboard window launcher.
* Natively integrated with `AyatanaAppIndicator3`—no fragile GNOME JavaScript extensions needed.

### 2. Dual Real-Time Vector Charts (Cairo Graphics)
* **+12V Main ATX Power Rail Stability**: High-resolution chart monitoring continuous PSU voltage against official ATX specifications (11.40V – 12.60V) with color-coded safety margins.
* **Combined & Per-GPU Wattage**: Multi-curve real-time power graph detailing CPU package wattage alongside every discrete GPU curve and total combined load.
* **Theme-Aware Color Palette**: Dynamically queries your active desktop GTK theme (`Gtk.StyleContext`) for accent and alert colors. Contrast engines ensure discrete GPUs and Total Power never collide.
* **Horizontal-Only Resizing**: Designed for multi-monitor and ultra-wide layouts; stretches horizontally while locking vertical height to keep system stats in view.

### 3. CPU & Multi-GPU Telemetry Engine
* **Intel & AMD CPU Package Power**: Direct energy tracking via Linux kernel Running Average Power Limit (RAPL). Includes udev rule (`99-power-monitor-rapl.rules`) for non-root access.
* **Multi-Vendor GPU Support**:
  * **NVIDIA**: Automatic NVML querying via `nvidia-smi` (power draw, thermals, GPU utilization).
  * **AMD Radeon**: Native kernel `hwmon` / `amdgpu` energy counters.
  * **Intel Arc**: Native `i915` / `xe` driver telemetry.
* **Motherboard Super I/O Database**: Zero-config resistor divider lookup for ASUS, MSI, and Gigabyte motherboards with automatic analog 12V heuristic fallback.

### 4. Background Daemon & Crash-Resilient Logging
* **Native systemd Integration**: Runs as a persistent background user service:
  ```bash
  systemctl --user enable --now power-monitor
  ```
* **Systemd Journal Telemetry**: Logs heartbeat metrics every 30s and priority alerts for voltage brownouts or GPU spikes:
  ```bash
  journalctl --user -u power-monitor -f
  ```
* **Flight Recorder CSV Mode**: On-demand millisecond-precision CSV capture with immediate flushing (`flush()`) to guarantee telemetry is saved right up to the moment of a brownout or hard crash.

---

## 🛠️ CLI Usage & Options

```text
usage: power-monitor [-h] [-v] [--no-gui] [--daemon] [--log-csv [PATH]] [--status] [--debug]

options:
  -h, --help        show this help message and exit
  -v, --version     show program's version number and exit
  --no-gui          start minimized as a top-panel indicator only
  --daemon          run in background as a headless systemd service logging to journald
  --log-csv [PATH]  record real-time telemetry samples to a CSV flight log
  --status          print instantaneous hardware snapshot to console and exit
  --debug           enable verbose debug logging
```

---

## 📄 License

GNU General Public License v3.0 or later (GPL-3.0-or-later).  
Developed by **Beno Labs** ([benolabsai.com](https://benolabsai.com)).
