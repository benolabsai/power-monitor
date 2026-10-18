# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-10-18

### Added
- **Version Number Display on GUI** — Integrated prominent release version badge (`v1.0.2`) directly into the GTK3 application header bar alongside the main title, with dynamic theme-aware styling.
- **Window Title Branding** — Appended release version to the primary dashboard window title (`Hardware Power & Voltage Monitor v1.0.2`).
- **Panel Indicator Branding** — Integrated release version number into the Ayatana top-panel dropdown menu title (`⚡ Power & Voltage Monitor v1.0.2`) and system desktop metadata.

---

## [1.0.1] - 2026-10-18

### Added
- **Threshold-Driven Immediate Event Logging** — Eliminated deferred reporting during critical power events. The daemon now immediately publishes and flushes events to `systemd-journald` the moment +12V rail voltage crosses safety margins:
  - `< 11.40V`: ATX specification undervoltage warning.
  - `< 11.00V`: Critical brownout collapse warning before PSU supervisory UVP can hard-reset the system.
  - `ΔV ≥ 0.35V drop`: Rapid voltage cliff detection on sudden di/dt transient surges.
  - Single recovery event documenting total sag duration (ms) and lowest voltage reached.
- **Per-Board Super I/O Divider Calibration (`--cal-12v`)** — Added one-step physical multimeter calibration to resolve board-specific resistor divider discrepancies across motherboard revisions:
  - Calculates exact divider multiplier based on user measurement (e.g. `power-monitor --cal-12v 12.18`).
  - Persists configuration automatically to `~/.config/power-monitor/calibration.json` (or `/etc/power-monitor/calibration.json`).
  - Added CLI overrides (`--v12-multiplier`, `--v12-offset`) and environment variable support (`POWER_MONITOR_V12_MULTIPLIER`, `POWER_MONITOR_V12_OFFSET`).
- **Direct NVML C-FFI GPU Telemetry** — Implemented direct C function calls via `ctypes` (`libnvidia-ml.so.1`), dropping NVIDIA polling latency from 50ms to 9 microseconds with zero subprocess forks.
- **Hardware Limitations & Calibration Documentation** — Added in-depth README documentation on millisecond-scale multi-GPU transient spikes, why periodic heartbeats mask brownouts, and physical multimeter probing procedures.

### Changed
- **Zero-Noise Daemon Mode** — Background daemon (`--daemon`) is now 100% silent while operating within normal bounds (11.40V – 12.60V), eliminating log pollution and reducing CPU duty cycle to <0.05%.

---

## [1.0.0] - 2026-10-18

### Added
- Initial community release.
- **Native GTK3 Interface** — Real-time telemetry dashboard with horizontal-only Cairo vector charts for +12V rail stability and per-GPU/CPU wattage curves.
- **Ayatana AppIndicator** — Real-time top-panel status indicator showing live voltage, power, and thermals.
- **Super I/O Database** — DMI-based motherboard database and heuristic 12V rail auto-detection for ASUS, MSI, and Gigabyte boards.
- **Multi-Vendor GPU Support** — Telemetry support for NVIDIA, AMD Radeon (amdgpu), and Intel Arc (i915/xe) GPUs.
- **CPU Package Energy Tracking** — Linux Running Average Power Limit (RAPL) integration with udev permission rules.
- **Crash-Resilient CSV Recording** — On-demand millisecond-precision CSV flight recorder with immediate `flush()`.
