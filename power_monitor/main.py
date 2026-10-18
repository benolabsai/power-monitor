"""
Hardware Power & Voltage Monitor Entrypoint.
Orchestrates hardware telemetry polling, GTK3 GUI, Ayatana AppIndicator,
and the threshold-driven systemd journal daemon.
"""

import os
import sys

pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if pkg_root not in sys.path:
    sys.path.insert(0, pkg_root)

import time
import argparse
import signal

from power_monitor import __version__, __app_name__
from power_monitor.sensors import TelemetryEngine
from power_monitor.system_logger import SystemJournalLogger
from power_monitor.database import save_calibration, load_calibration

def run_headless_daemon(interval: float = 0.2, debug: bool = False, keepalive_sec: float = 300.0):
    """
    Runs as an ultra-low-overhead background daemon.
    Zero noise while operating within normal bounds.
    Immediately event-logs to system journal when passing specific thresholds (<11.40V, <11.00V).
    """
    print(f"[{__app_name__}] Starting threshold-driven daemon (poll: {interval*1000:.0f}ms, keepalive: {keepalive_sec:.0f}s)")
    print(f"[{__app_name__}] Completely silent in bounds; immediate event dispatch to journald on voltage sag.")

    engine = TelemetryEngine()
    journal_logger = SystemJournalLogger(heartbeat_interval=keepalive_sec)

    running = True

    def sig_handler(sig, frame):
        nonlocal running
        print(f"[{__app_name__}] Received stop signal, shutting down cleanly...")
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    while running:
        try:
            stats = engine.poll()
            journal_logger.inspect_frame(stats)
        except Exception as e:
            if debug:
                print(f"[{__app_name__}] Telemetry poll exception: {e}", file=sys.stderr)
        time.sleep(interval)

    print(f"[{__app_name__}] Daemon stopped.")

def run_gui_application(no_gui: bool = False, debug: bool = False):
    """Runs the interactive desktop application with GTK3 GUI and top-panel indicator."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    from power_monitor.gui import MainWindow
    from power_monitor.indicator import PowerMonitorIndicator
    import threading

    class Application:
        def __init__(self):
            self.debug = debug
            self.running = True

            self.engine = TelemetryEngine()

            self.indicator = PowerMonitorIndicator(
                on_toggle_gui=self.toggle_gui,
                on_quit=self.quit
            )

            self.window = MainWindow(
                hide_on_close=True,
                on_quit_callback=self.quit
            )

            if not no_gui:
                self.window.show_all()
                self.window.present()

            GLib.timeout_add_seconds(1, self.trigger_poll)
            self.trigger_poll()

        def toggle_gui(self):
            if self.window.is_visible():
                self.window.hide()
            else:
                self.window.show_all()
                self.window.present()

        def trigger_poll(self):
            def worker():
                stats = self.engine.poll()
                if self.running:
                    GLib.idle_add(self._on_telemetry_ready, stats)

            threading.Thread(target=worker, daemon=True).start()
            return self.running

        def _on_telemetry_ready(self, stats):
            if not self.running:
                return False
            self.window.update_telemetry(stats)
            self.indicator.update_telemetry(stats)
            return False

        def quit(self):
            self.running = False
            Gtk.main_quit()

    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    app = Application()
    Gtk.main()

def main():
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="Hardware Power & Voltage Telemetry Monitor with Desktop Panel Indicator and Event-Driven Journal Daemon."
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--daemon", action="store_true", help="Run as a headless background daemon (immediately logs threshold breach events to journald).")
    parser.add_argument("--interval", type=float, default=0.2, help="Polling interval in seconds (default: 0.2s / 200ms).")
    parser.add_argument("--keepalive", type=float, default=300.0, help="Slow keepalive interval when healthy in seconds (default: 300s, <=0 disables).")
    parser.add_argument("--no-gui", action="store_true", help="Start minimized as a top-panel indicator only.")
    parser.add_argument("--status", action="store_true", help="Print instantaneous hardware snapshot to console and exit.")
    parser.add_argument("--cal-12v", type=float, default=None, metavar="VOLTS",
                        help="Calibrate +12V rail against a physical multimeter measurement on a spare PCIe lead (e.g. --cal-12v 12.18).")
    parser.add_argument("--v12-multiplier", type=float, default=None, metavar="MULT",
                        help="Override +12V rail multiplier factor.")
    parser.add_argument("--v12-offset", type=float, default=None, metavar="VOLTS",
                        help="Override +12V rail offset in Volts.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug output.")

    args = parser.parse_args()

    # 1. Calibration mode
    if args.cal_12v is not None:
        target_v = args.cal_12v
        print(f"[{__app_name__}] Performing +12V rail hardware calibration...")
        engine = TelemetryEngine(v12_multiplier=1.0, v12_offset=0.0)
        samples = []
        for _ in range(5):
            stats = engine.poll()
            if stats.get("12v") is not None:
                samples.append(stats["12v"])
            time.sleep(0.05)

        if not samples:
            print(f"[{__app_name__}] ERROR: Unable to detect +12V rail sensor on this motherboard.", file=sys.stderr)
            sys.exit(1)

        raw_v = sum(samples) / len(samples)
        src = stats.get("12v_source", "Super I/O")
        mult, saved_path = save_calibration(target_v, raw_v, src)

        print("=" * 68)
        print(f"⚡ {__app_name__} - +12V Rail Calibration Complete")
        print("=" * 68)
        print(f"  Physical Multimeter Reading : {target_v:.3f} V")
        print(f"  Uncalibrated Sensor Voltage : {raw_v:.3f} V  ({src})")
        print(f"  Calculated Divider Multiplier: {mult:.6f}x")
        print(f"  Configuration Saved To      : {saved_path}")
        print("=" * 68)
        print("All future runs will automatically apply this hardware correction.")
        sys.exit(0)

    # 2. Instantaneous snapshot
    if args.status:
        import pprint
        engine = TelemetryEngine(v12_multiplier=args.v12_multiplier, v12_offset=args.v12_offset)
        stats = engine.poll()
        pprint.pprint(stats)
        sys.exit(0)

    # 3. Headless daemon or GUI
    if args.daemon:
        run_headless_daemon(interval=args.interval, debug=args.debug, keepalive_sec=args.keepalive)
    else:
        run_gui_application(no_gui=args.no_gui, debug=args.debug)

if __name__ == "__main__":
    main()
