"""
Desktop Top-Panel Indicator using AyatanaAppIndicator3.
Displays live +12V rail voltage and total wattage in the Ubuntu top bar,
and provides quick status and dashboard access.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, AyatanaAppIndicator3
from typing import Optional, Callable
from power_monitor import __version__

class PowerMonitorIndicator:
    def __init__(
        self,
        on_toggle_gui: Optional[Callable] = None,
        on_quit: Optional[Callable] = None
    ):
        self.on_toggle_gui = on_toggle_gui
        self.on_quit = on_quit

        # Initialize Ayatana Indicator
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "power-monitor",
            "battery-charging-symbolic",
            AyatanaAppIndicator3.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title(f"Power Monitor v{__version__}")
        self.indicator.set_label("⚡ 12.00V | 000W", "⚡ 12.00V | 999W")

        self.setup_menu()

    def setup_menu(self):
        self.menu = Gtk.Menu()

        # Header title
        self.item_title = Gtk.MenuItem(label=f"⚡ Power & Voltage Monitor v{__version__}")
        self.item_title.set_sensitive(False)
        self.menu.append(self.item_title)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Live status items
        self.item_12v = Gtk.MenuItem(label="+12V Rail: --.-- V")
        self.item_12v.set_sensitive(False)
        self.menu.append(self.item_12v)

        self.item_power = Gtk.MenuItem(label="Total Power: --.- W")
        self.item_power.set_sensitive(False)
        self.menu.append(self.item_power)

        self.item_temps = Gtk.MenuItem(label="CPU: -- °C  |  GPU: -- °C")
        self.item_temps.set_sensitive(False)
        self.menu.append(self.item_temps)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Action: Show / Hide Dashboard
        self.item_dashboard = Gtk.MenuItem(label="Show Dashboard")
        self.item_dashboard.connect("activate", self._handle_toggle_gui)
        self.menu.append(self.item_dashboard)

        # Action: Quit
        self.item_quit = Gtk.MenuItem(label="Quit")
        self.item_quit.connect("activate", self._handle_quit)
        self.menu.append(self.item_quit)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _handle_toggle_gui(self, widget):
        if self.on_toggle_gui:
            self.on_toggle_gui()

    def _handle_quit(self, widget):
        if self.on_quit:
            self.on_quit()
        else:
            Gtk.main_quit()

    def update_telemetry(self, stats: dict):
        """Updates the indicator label in the panel and the dropdown menu."""
        v12 = stats.get("12v")
        gpus = stats.get("gpus", [])
        gpu_pwr_total = sum(g.get("power", 0.0) for g in gpus)
        cpu_pwr = stats.get("cpu_power")
        total_pwr = gpu_pwr_total + (cpu_pwr if cpu_pwr is not None else 0.0)

        cpu_temp = stats.get("cpu_temp")
        gpu_temp = gpus[0].get("temp") if gpus else None

        v12_str = f"{v12:.2f}V" if v12 is not None else "--.--V"
        pwr_str = f"{total_pwr:.0f}W"

        # Update top bar label
        label_text = f"⚡ {v12_str} | {pwr_str}"
        self.indicator.set_label(label_text, "⚡ 12.00V | 999W")

        # Update menu items
        if v12 is not None:
            status_text = "Within ATX Spec" if 11.40 <= v12 <= 12.60 else "Out of Spec"
            self.item_12v.set_label(f"+12V Rail: {v12:.2f} V ({status_text})")

        self.item_power.set_label(f"Total Power: {total_pwr:.1f} W")

        cpu_p_str = f" ({cpu_pwr:.0f}W)" if cpu_pwr is not None else ""
        cpu_s = f"{cpu_temp:.0f} °C{cpu_p_str}" if cpu_temp is not None else "--"
        gpu_s = f"{gpu_temp:.0f} °C" if gpu_temp is not None else "--"
        self.item_temps.set_label(f"CPU: {cpu_s}  |  GPU: {gpu_s}")
