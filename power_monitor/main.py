"""
Hardware Power & Voltage Monitor Entrypoint.
Orchestrates hardware telemetry polling, GTK3 GUI, Ayatana AppIndicator,
and the systemd journal background daemon.
"""

import os
import sys

# Ensure package root is in path when executed directly
pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if pkg_root not in sys.path:
    sys.path.insert(0, pkg_root)

import time
import argparse
import signal

from power_monitor import __version__, __app_name__
from power_monitor.sensors import TelemetryEngine
from power_monitor.system_logger import SystemJournalLogger

def run_headless_daemon(interval: float = 1.0, debug: bool = False):
    """
    Runs as a headless background daemon or systemd service without GTK or display dependencies.
    Logs rail stability events and heartbeats directly into the system journal (journald/syslog).
    """
    print(f"[{__app_name__}] Starting headless background daemon (interval: {interval}s)")
    print(f"[{__app_name__}] Diagnostic events will be dispatched to system journal (journalctl -u power-monitor)")

    engine = TelemetryEngine()
    journal_logger = SystemJournalLogger(heartbeat_interval=30.0)

    running = True

    def sig_handler(sig, frame):
        nonlocal running
        print(f"\n[{__app_name__}] Received stop signal, shutting down daemon cleanly...")
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
        description="Universal Hardware Power & Voltage Telemetry Monitor with Desktop Panel Indicator and Systemd Daemon."
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--daemon", action="store_true", help="Run as a headless background daemon (logs anomalies to systemd journal).")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds (default: 1.0).")
    parser.add_argument("--no-gui", action="store_true", help="Start minimized as a top-panel indicator only.")
    parser.add_argument("--status", action="store_true", help="Print instantaneous hardware snapshot to console and exit.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug output.")

    args = parser.parse_args()

    if args.status:
        import pprint
        engine = TelemetryEngine()
        stats = engine.poll()
        pprint.pprint(stats)
        sys.exit(0)

    if args.daemon:
        run_headless_daemon(interval=args.interval, debug=args.debug)
    else:
        run_gui_application(no_gui=args.no_gui, debug=args.debug)

if __name__ == "__main__":
    main()
