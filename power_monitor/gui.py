"""
Native GTK3 GUI Window with Cairo Vector Charts.
Features horizontally-resizable charts with locked vertical heights,
multi-GPU and CPU package power tracking, and automatic desktop theme synchronization.
"""

import time
from collections import deque
from typing import Dict, List, Any, Optional, Callable

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib
import cairo

from power_monitor.database import get_dmi_info

GTK_THEME_CSS = b"""
window {
    background-color: @theme_bg_color;
}
.card {
    background-color: alpha(@theme_fg_color, 0.05);
    border: 1px solid alpha(@theme_fg_color, 0.12);
    border-radius: 8px;
    padding: 8px;
}
.hero-card {
    background-color: alpha(@theme_selected_bg_color, 0.08);
    border: 1px solid alpha(@theme_selected_bg_color, 0.30);
    border-radius: 10px;
    padding: 10px;
}
.hero-title {
    font-size: 8.5pt;
    font-weight: bold;
    color: @theme_selected_bg_color;
}
.hero-voltage {
    font-size: 26pt;
    font-weight: 800;
    color: @theme_selected_bg_color;
}
.hero-wattage {
    font-size: 26pt;
    font-weight: 800;
    color: @theme_fg_color;
}
.status-pill {
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: bold;
    font-size: 8pt;
}
.status-healthy {
    background-color: alpha(#2ea043, 0.22);
    color: #2ea043;
}
.status-warning {
    background-color: alpha(#d29922, 0.22);
    color: #d29922;
}
.status-critical {
    background-color: alpha(#cf222e, 0.22);
    color: #cf222e;
}
.metric-header {
    font-size: 8pt;
    font-weight: bold;
    opacity: 0.70;
}
.metric-val {
    font-size: 13pt;
    font-weight: bold;
}
.metric-desc {
    font-size: 7.5pt;
    opacity: 0.60;
}
.vendor-badge {
    font-size: 7.5pt;
    font-weight: bold;
    padding: 1px 6px;
    border-radius: 4px;
}
.vendor-nvidia {
    background-color: alpha(#76b900, 0.20);
    color: #76b900;
}
.vendor-amd {
    background-color: alpha(#ed1c24, 0.20);
    color: #ed1c24;
}
.vendor-intel {
    background-color: alpha(#0071c5, 0.20);
    color: #0071c5;
}
"""

CPU_COLOR = (0.96, 0.62, 0.13)  # Amber / Orange (#f59e0b) for CPU Package

GPU_COLORS = [
    (0.20, 0.75, 0.98),  # GPU 0: Vibrant Cyan (#33befa)
    (0.70, 0.35, 0.98),  # GPU 1: Vibrant Purple (#b359fa)
    (0.22, 0.82, 0.64),  # GPU 2: Emerald Green (#34d399)
    (0.93, 0.28, 0.60),  # GPU 3: Rose (#ec4899)
]

def get_cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "Processor"

class MainWindow(Gtk.Window):
    def __init__(self, hide_on_close: bool = False, on_quit_callback: Optional[Callable] = None):
        super().__init__(title="Hardware Power & Voltage Monitor")
        self.set_default_size(880, 760)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.hide_on_close = hide_on_close
        self.on_quit_callback = on_quit_callback

        self.sync_system_theme()

        vendor, model = get_dmi_info()
        self.mb_desc = f"{vendor} {model}"
        self.cpu_desc = get_cpu_model()

        # Telemetry histories
        self.history_12v = deque(maxlen=60)
        self.min_12v = None
        self.max_12v = None

        self.history_total_pwr = deque(maxlen=60)
        self.history_cpu_pwr = deque(maxlen=60)
        self.history_gpu_pwr = {}
        self.max_total_pwr = 0.0

        self.gpu_cards = []
        self.system_metric_labels = {}
        self.current_gpus = []

        self.setup_css()
        self.setup_ui()

        self.connect("delete-event", self.on_delete_event)

    def sync_system_theme(self):
        try:
            self.gsettings = Gio.Settings.new("org.gnome.desktop.interface")
            scheme = self.gsettings.get_string("color-scheme")
            is_dark = (scheme == "prefer-dark")
            gtk_settings = Gtk.Settings.get_default()
            gtk_settings.set_property("gtk-application-prefer-dark-theme", is_dark)
            self.gsettings.connect("changed::color-scheme", self.on_theme_changed)
        except Exception:
            pass

    def on_theme_changed(self, settings, key):
        try:
            scheme = settings.get_string("color-scheme")
            gtk_settings = Gtk.Settings.get_default()
            gtk_settings.set_property("gtk-application-prefer-dark-theme", scheme == "prefer-dark")
            self.queue_draw()
        except Exception:
            pass

    def setup_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(GTK_THEME_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def setup_ui(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add(scroller)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_hexpand(True)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        main_box.set_margin_top(14)
        main_box.set_margin_bottom(14)
        scroller.add(main_box)

        # Header
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_box.set_hexpand(True)
        main_box.pack_start(header_box, False, False, 0)

        title_lbl = Gtk.Label(xalign=0)
        title_lbl.set_markup("<b><big>⚡ Hardware Power &amp; Voltage Monitor</big></b>")
        header_box.pack_start(title_lbl, False, False, 0)

        self.sub_lbl = Gtk.Label(xalign=0)
        self.sub_lbl.set_markup(f"<small>{GLib.markup_escape_text(self.mb_desc)} • {GLib.markup_escape_text(self.cpu_desc)}</small>")
        header_box.pack_start(self.sub_lbl, False, False, 0)

        # -------------------------------------------------------------
        # CHART 1: +12V MAIN POWER INPUT (VOLTAGE STABILITY)
        # -------------------------------------------------------------
        hero_frame = Gtk.Frame()
        hero_frame.set_shadow_type(Gtk.ShadowType.NONE)
        hero_frame.set_hexpand(True)
        hero_frame.set_vexpand(False)
        hero_frame.get_style_context().add_class("hero-card")
        main_box.pack_start(hero_frame, False, True, 0)

        hero_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hero_box.set_hexpand(True)
        hero_frame.add(hero_box)

        card_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        card_top.set_hexpand(True)
        hero_box.pack_start(card_top, False, False, 0)

        lbl_12v_tag = Gtk.Label(label="MAIN POWER INPUT (+12V ATX / PSU RAIL)", xalign=0)
        lbl_12v_tag.get_style_context().add_class("hero-title")
        card_top.pack_start(lbl_12v_tag, True, True, 0)

        self.status_badge = Gtk.Label(label="● Healthy (11.4V - 12.6V)")
        self.status_badge.get_style_context().add_class("status-pill")
        self.status_badge.get_style_context().add_class("status-healthy")
        card_top.pack_end(self.status_badge, False, False, 0)

        val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        val_row.set_hexpand(True)
        hero_box.pack_start(val_row, False, False, 0)

        self.val_12v_lbl = Gtk.Label(label="--.-- V", xalign=0)
        self.val_12v_lbl.get_style_context().add_class("hero-voltage")
        val_row.pack_start(self.val_12v_lbl, False, False, 0)

        self.stats_12v_lbl = Gtk.Label(label="Min: -- V  |  Max: -- V", xalign=1)
        self.stats_12v_lbl.get_style_context().add_class("metric-desc")
        val_row.pack_end(self.stats_12v_lbl, True, True, 0)

        # Cairo Voltage Graph: Expands Horizontally, Locked Vertically (85px)
        self.graph_area_v = Gtk.DrawingArea()
        self.graph_area_v.set_size_request(-1, 85)
        self.graph_area_v.set_hexpand(True)
        self.graph_area_v.set_vexpand(False)
        self.graph_area_v.connect("draw", self.on_draw_voltage_graph)
        self.graph_area_v.connect("size-allocate", lambda w, a: w.queue_draw())
        hero_box.pack_start(self.graph_area_v, False, True, 0)

        # -------------------------------------------------------------
        # CHART 2: CPU, PER-GPU & TOTAL WATTAGE IN USE (REAL-TIME CHART)
        # -------------------------------------------------------------
        wattage_frame = Gtk.Frame()
        wattage_frame.set_shadow_type(Gtk.ShadowType.NONE)
        wattage_frame.set_hexpand(True)
        wattage_frame.set_vexpand(False)
        wattage_frame.get_style_context().add_class("card")
        main_box.pack_start(wattage_frame, False, True, 0)

        wattage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        wattage_box.set_hexpand(True)
        wattage_frame.add(wattage_box)

        w_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        w_top.set_hexpand(True)
        wattage_box.pack_start(w_top, False, False, 0)

        lbl_w_tag = Gtk.Label(label="POWER CONSUMPTION (CPU, PER-GPU & TOTAL WATTAGE)", xalign=0)
        lbl_w_tag.get_style_context().add_class("metric-header")
        w_top.pack_start(lbl_w_tag, True, True, 0)

        self.stats_pwr_peak_lbl = Gtk.Label(label="Peak: -- W", xalign=1)
        self.stats_pwr_peak_lbl.get_style_context().add_class("metric-desc")
        w_top.pack_end(self.stats_pwr_peak_lbl, False, False, 0)

        w_val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        w_val_row.set_hexpand(True)
        wattage_box.pack_start(w_val_row, False, False, 0)

        self.val_total_pwr_lbl = Gtk.Label(label="--.- W", xalign=0)
        self.val_total_pwr_lbl.get_style_context().add_class("hero-wattage")
        w_val_row.pack_start(self.val_total_pwr_lbl, False, False, 0)

        self.legend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        w_val_row.pack_end(self.legend_box, True, True, 0)

        # Cairo Multi-Line Wattage Graph: Expands Horizontally, Locked Vertically (110px)
        self.graph_area_w = Gtk.DrawingArea()
        self.graph_area_w.set_size_request(-1, 110)
        self.graph_area_w.set_hexpand(True)
        self.graph_area_w.set_vexpand(False)
        self.graph_area_w.connect("draw", self.on_draw_wattage_graph)
        self.graph_area_w.connect("size-allocate", lambda w, a: w.queue_draw())
        wattage_box.pack_start(self.graph_area_w, False, True, 0)

        # -------------------------------------------------------------
        # GPU Telemetry Cards Section
        # -------------------------------------------------------------
        gpu_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        gpu_hdr.set_hexpand(True)
        main_box.pack_start(gpu_hdr, False, False, 2)

        lbl_gpu_sec = Gtk.Label(xalign=0)
        lbl_gpu_sec.set_markup("<b>GPU HARDWARE TELEMETRY</b>")
        gpu_hdr.pack_start(lbl_gpu_sec, True, True, 0)

        self.gpus_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.gpus_container.set_hexpand(True)
        main_box.pack_start(self.gpus_container, False, True, 0)

        # -------------------------------------------------------------
        # System Rails & Sensors (3x2 Grid)
        # -------------------------------------------------------------
        sys_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sys_hdr.set_hexpand(True)
        main_box.pack_start(sys_hdr, False, False, 2)

        lbl_sys_sec = Gtk.Label(xalign=0)
        lbl_sys_sec.set_markup("<b>SYSTEM RAILS &amp; SENSORS</b>")
        sys_hdr.pack_start(lbl_sys_sec, True, True, 0)

        sys_grid = Gtk.Grid()
        sys_grid.set_column_spacing(8)
        sys_grid.set_row_spacing(8)
        sys_grid.set_column_homogeneous(True)
        sys_grid.set_row_homogeneous(True)
        sys_grid.set_hexpand(True)
        main_box.pack_start(sys_grid, False, True, 0)

        sys_metrics = [
            ("3v3", "+3.3V Rail", "ATX 3.3V Spec"),
            ("vcore", "CPU Core Voltage", "Vcore Sensor"),
            ("cpu_temp", "CPU Temperature", "AMD / Intel Sensor"),
            ("cpu_fan", "CPU Cooler Fan", "Primary Fan Header"),
            ("mb_temp", "Motherboard Temp", "System Sensor"),
            ("chassis_fan", "Chassis Fan", "Case Fan Header"),
        ]

        for i, (key, label, desc) in enumerate(sys_metrics):
            row = i // 3
            col = i % 3

            card_frame = Gtk.Frame()
            card_frame.set_shadow_type(Gtk.ShadowType.NONE)
            card_frame.set_hexpand(True)
            card_frame.get_style_context().add_class("card")
            sys_grid.attach(card_frame, col, row, 1, 1)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card_frame.add(box)

            tl = Gtk.Label(label=label, xalign=0)
            tl.get_style_context().add_class("metric-header")
            box.pack_start(tl, False, False, 0)

            vl = Gtk.Label(label="--", xalign=0)
            vl.get_style_context().add_class("metric-val")
            box.pack_start(vl, False, False, 0)

            dl = Gtk.Label(label=desc, xalign=0)
            dl.get_style_context().add_class("metric-desc")
            box.pack_start(dl, False, False, 0)

            self.system_metric_labels[key] = vl

        # Footer
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer_box.set_hexpand(True)
        main_box.pack_end(footer_box, False, False, 0)

        self.last_update_lbl = Gtk.Label(label="Initializing telemetry...", xalign=0)
        self.last_update_lbl.get_style_context().add_class("metric-desc")
        footer_box.pack_start(self.last_update_lbl, True, True, 0)

        reset_btn = Gtk.Button(label="Reset Min/Max & Peaks")
        reset_btn.connect("clicked", self.on_reset_stats)
        footer_box.pack_end(reset_btn, False, False, 0)

    def on_delete_event(self, widget, event):
        if self.hide_on_close:
            self.hide()
            return True
        if self.on_quit_callback:
            self.on_quit_callback()
        Gtk.main_quit()
        return False

    def on_reset_stats(self, widget):
        self.min_12v = None
        self.max_12v = None
        self.history_12v.clear()
        self.history_total_pwr.clear()
        self.history_cpu_pwr.clear()
        self.history_gpu_pwr.clear()
        self.max_total_pwr = 0.0
        self.graph_area_v.queue_draw()
        self.graph_area_w.queue_draw()

    def update_telemetry(self, stats: Dict[str, Any]):
        # 1. Update 12V Rail
        v12 = stats.get("12v")
        v12_src = stats.get("12v_source", "")
        if v12 is not None:
            self.val_12v_lbl.set_text(f"{v12:.2f} V")
            self.history_12v.append(v12)

            if self.min_12v is None or v12 < self.min_12v:
                self.min_12v = v12
            if self.max_12v is None or v12 > self.max_12v:
                self.max_12v = v12

            self.stats_12v_lbl.set_text(
                f"Min: {self.min_12v:.2f} V   Max: {self.max_12v:.2f} V   [{v12_src}]"
            )

            sc = self.status_badge.get_style_context()
            sc.remove_class("status-healthy")
            sc.remove_class("status-warning")
            sc.remove_class("status-critical")

            if 11.40 <= v12 <= 12.60:
                self.status_badge.set_text("● Healthy (Within ATX Spec)")
                sc.add_class("status-healthy")
            elif 11.00 <= v12 < 11.40 or 12.60 < v12 <= 13.00:
                self.status_badge.set_text("▲ Warning (Near Margin)")
                sc.add_class("status-warning")
            else:
                self.status_badge.set_text("✖ Critical (Out of Spec)")
                sc.add_class("status-critical")

            self.graph_area_v.queue_draw()

        # 2. Update Wattage (CPU + GPUs)
        gpus = stats.get("gpus", [])
        self.current_gpus = gpus
        gpu_pwr_total = sum(g.get("power", 0.0) for g in gpus)
        cpu_pwr = stats.get("cpu_power")

        if cpu_pwr is not None:
            self.history_cpu_pwr.append(cpu_pwr)
            total_pwr = gpu_pwr_total + cpu_pwr
        else:
            total_pwr = gpu_pwr_total

        self.history_total_pwr.append(total_pwr)

        if total_pwr > self.max_total_pwr:
            self.max_total_pwr = total_pwr

        for gpu in gpus:
            idx = gpu["idx"]
            if idx not in self.history_gpu_pwr:
                self.history_gpu_pwr[idx] = deque(maxlen=60)
            self.history_gpu_pwr[idx].append(gpu["power"])

        self.val_total_pwr_lbl.set_text(f"{total_pwr:.1f} W")
        self.stats_pwr_peak_lbl.set_text(f"Peak Total: {self.max_total_pwr:.1f} W")

        # Dynamic Legend
        for child in self.legend_box.get_children():
            self.legend_box.remove(child)

        lbl_tot = Gtk.Label(xalign=1)
        lbl_tot.set_markup(f"<b><span foreground='#38bdf8'>■ Total:</span></b> {total_pwr:.1f} W")
        self.legend_box.pack_start(lbl_tot, False, False, 4)

        if cpu_pwr is not None:
            lbl_cpu = Gtk.Label(xalign=1)
            lbl_cpu.set_markup(f"<b><span foreground='#f59e0b'>■ CPU:</span></b> {cpu_pwr:.1f} W")
            self.legend_box.pack_start(lbl_cpu, False, False, 4)

        for gpu in gpus:
            color = GPU_COLORS[gpu["idx"] % len(GPU_COLORS)]
            hex_c = f"#{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}"
            lbl_g = Gtk.Label(xalign=1)
            lbl_g.set_markup(f"<b><span foreground='{hex_c}'>■ GPU {gpu['idx']}:</span></b> {gpu['power']:.1f} W")
            self.legend_box.pack_start(lbl_g, False, False, 4)

        self.legend_box.show_all()
        self.graph_area_w.queue_draw()

        # 3. Synchronize GPU cards
        if len(self.gpu_cards) != len(gpus):
            for child in self.gpus_container.get_children():
                self.gpus_container.remove(child)
            self.gpu_cards.clear()

            for gpu in gpus:
                frame = Gtk.Frame()
                frame.set_shadow_type(Gtk.ShadowType.NONE)
                frame.set_hexpand(True)
                frame.get_style_context().add_class("card")
                self.gpus_container.pack_start(frame, False, True, 0)

                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                box.set_hexpand(True)
                frame.add(box)

                r1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                r1.set_hexpand(True)
                box.pack_start(r1, False, False, 0)

                v_badge = Gtk.Label(label=f"[{gpu['vendor']}]")
                v_badge.get_style_context().add_class("vendor-badge")
                v_badge.get_style_context().add_class(f"vendor-{gpu['vendor'].lower()}")
                r1.pack_start(v_badge, False, False, 0)

                name_l = Gtk.Label(xalign=0)
                name_l.set_markup(f"<b>GPU {gpu['idx']}: {GLib.markup_escape_text(gpu['name'])}</b>")
                r1.pack_start(name_l, True, True, 0)

                pcie_l = Gtk.Label(label=gpu["pcie"], xalign=1)
                pcie_l.get_style_context().add_class("hero-title")
                r1.pack_end(pcie_l, False, False, 0)

                r2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                r2.set_hexpand(True)
                box.pack_start(r2, False, False, 0)

                lim_str = f" / {gpu['power_limit']:.0f} W" if gpu['power_limit'] > 0 else ""
                pwr_l = Gtk.Label(label=f"Power: {gpu['power']:.1f} W{lim_str}", xalign=0)
                pwr_l.get_style_context().add_class("hero-title")
                r2.pack_start(pwr_l, False, False, 0)

                temp_l = Gtk.Label(label=f"Temp: {gpu['temp']:.0f} °C", xalign=0)
                r2.pack_start(temp_l, False, False, 0)

                util_l = Gtk.Label(label=f"Load: {gpu['util']:.0f}%", xalign=0)
                r2.pack_start(util_l, False, False, 0)

                vram_l = Gtk.Label(label=f"VRAM: {gpu['mem_used']:.1f}/{gpu['mem_total']:.1f} GB" if gpu['mem_total'] > 0 else "VRAM: --", xalign=1)
                vram_l.get_style_context().add_class("metric-desc")
                r2.pack_end(vram_l, True, True, 0)

                frame.show_all()
                self.gpu_cards.append({
                    "pcie": pcie_l,
                    "power": pwr_l,
                    "temp": temp_l,
                    "util": util_l,
                    "vram": vram_l
                })
        else:
            for i, gpu in enumerate(gpus):
                card = self.gpu_cards[i]
                card["pcie"].set_text(gpu["pcie"])
                lim_str = f" / {gpu['power_limit']:.0f} W" if gpu['power_limit'] > 0 else ""
                card["power"].set_text(f"Power: {gpu['power']:.1f} W{lim_str}")
                card["temp"].set_text(f"Temp: {gpu['temp']:.0f} °C")
                card["util"].set_text(f"Load: {gpu['util']:.0f}%")
                if gpu['mem_total'] > 0:
                    card["vram"].set_text(f"VRAM: {gpu['mem_used']:.1f}/{gpu['mem_total']:.1f} GB")

        # 4. Update System Metrics
        if "3v3" in stats:
            self.system_metric_labels["3v3"].set_text(f"{stats['3v3']:.2f} V")
        if "vcore" in stats:
            self.system_metric_labels["vcore"].set_text(f"{stats['vcore']:.2f} V")
        if "cpu_temp" in stats:
            cpu_p_str = f" ({cpu_pwr:.0f} W)" if cpu_pwr is not None else ""
            self.system_metric_labels["cpu_temp"].set_text(f"{stats['cpu_temp']:.1f} °C{cpu_p_str}")
        if "cpu_fan" in stats:
            self.system_metric_labels["cpu_fan"].set_text(f"{stats['cpu_fan']} RPM")
        if "mb_temp" in stats:
            self.system_metric_labels["mb_temp"].set_text(f"{stats['mb_temp']:.1f} °C")
        if "chassis_fan" in stats:
            self.system_metric_labels["chassis_fan"].set_text(f"{stats['chassis_fan']} RPM")

        self.last_update_lbl.set_text(
            f"Live • Last updated: {time.strftime('%H:%M:%S')}"
        )

    def on_draw_voltage_graph(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        if w < 10 or h < 10:
            return False

        style_context = widget.get_style_context()
        fg_color = style_context.get_color(Gtk.StateFlags.NORMAL)
        sel_color = style_context.get_color(Gtk.StateFlags.SELECTED)

        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.04)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        y_min = 11.0
        y_max = 13.0

        def to_y(val):
            ratio = (val - y_min) / (y_max - y_min)
            return h - (ratio * h)

        cr.set_line_width(1.0)
        cr.set_dash([3, 4], 0)

        # 12.6V Max
        y_12_6 = to_y(12.6)
        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.18)
        cr.move_to(0, y_12_6)
        cr.line_to(w, y_12_6)
        cr.stroke()

        # 12.0V Target line (Green)
        y_12_0 = to_y(12.0)
        cr.set_source_rgba(0.18, 0.63, 0.26, 0.60)
        cr.move_to(0, y_12_0)
        cr.line_to(w, y_12_0)
        cr.stroke()

        # 11.4V Min
        y_11_4 = to_y(11.4)
        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.18)
        cr.move_to(0, y_11_4)
        cr.line_to(w, y_11_4)
        cr.stroke()

        cr.set_dash([], 0)

        pts = list(self.history_12v)
        if len(pts) >= 2:
            x_step = w / 59.0
            start_idx = 60 - len(pts)

            coords = []
            for i, val in enumerate(pts):
                x = (start_idx + i) * x_step
                y = max(2, min(h - 2, to_y(val)))
                coords.append((x, y))

            cr.set_source_rgba(sel_color.red, sel_color.green, sel_color.blue, 0.95)
            cr.set_line_width(2.2)

            cr.move_to(coords[0][0], coords[0][1])
            for pt in coords[1:]:
                cr.line_to(pt[0], pt[1])
            cr.stroke()

            last_x, last_y = coords[-1]
            cr.arc(last_x, last_y, 4.0, 0, 2 * 3.14159)
            cr.set_source_rgba(sel_color.red, sel_color.green, sel_color.blue, 1.0)
            cr.fill_preserve()
            cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.8)
            cr.set_line_width(1.0)
            cr.stroke()

        return True

    def on_draw_wattage_graph(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        if w < 10 or h < 10:
            return False

        style_context = widget.get_style_context()
        fg_color = style_context.get_color(Gtk.StateFlags.NORMAL)

        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.04)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        max_seen = max(100.0, self.max_total_pwr * 1.2)
        y_max = float(((int(max_seen) + 49) // 50) * 50)

        def to_y(val):
            ratio = val / y_max
            return h - (ratio * (h - 10)) - 5

        cr.set_line_width(1.0)
        cr.set_dash([3, 4], 0)
        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, 0.15)

        for step in [0.25, 0.50, 0.75, 1.0]:
            y_val = y_max * step
            y_pos = to_y(y_val)
            cr.move_to(0, y_pos)
            cr.line_to(w, y_pos)
            cr.stroke()

        cr.set_dash([], 0)

        # 1. Total Power fill & line (Cyan gradient)
        tot_pts = list(self.history_total_pwr)
        if len(tot_pts) >= 2:
            x_step = w / 59.0
            start_idx = 60 - len(tot_pts)

            coords = []
            for i, val in enumerate(tot_pts):
                x = (start_idx + i) * x_step
                y = max(2, min(h - 2, to_y(val)))
                coords.append((x, y))

            cr.move_to(coords[0][0], h)
            for pt in coords:
                cr.line_to(pt[0], pt[1])
            cr.line_to(coords[-1][0], h)
            cr.close_path()
            cr.set_source_rgba(0.22, 0.74, 0.97, 0.14)
            cr.fill()

            cr.set_source_rgba(0.22, 0.74, 0.97, 0.90)
            cr.set_line_width(2.5)
            cr.move_to(coords[0][0], coords[0][1])
            for pt in coords[1:]:
                cr.line_to(pt[0], pt[1])
            cr.stroke()

        # 2. CPU Package Power Curve (Amber / Orange)
        cpu_pts = list(self.history_cpu_pwr)
        if len(cpu_pts) >= 2:
            x_step = w / 59.0
            start_idx = 60 - len(cpu_pts)

            coords = []
            for i, val in enumerate(cpu_pts):
                x = (start_idx + i) * x_step
                y = max(2, min(h - 2, to_y(val)))
                coords.append((x, y))

            cr.set_source_rgba(CPU_COLOR[0], CPU_COLOR[1], CPU_COLOR[2], 0.95)
            cr.set_line_width(1.8)
            cr.move_to(coords[0][0], coords[0][1])
            for pt in coords[1:]:
                cr.line_to(pt[0], pt[1])
            cr.stroke()

            last_x, last_y = coords[-1]
            cr.arc(last_x, last_y, 3.5, 0, 2 * 3.14159)
            cr.fill()

        # 3. Per-GPU Individual Curves
        for gpu_idx, pts_deque in self.history_gpu_pwr.items():
            pts = list(pts_deque)
            if len(pts) >= 2:
                color = GPU_COLORS[gpu_idx % len(GPU_COLORS)]
                x_step = w / 59.0
                start_idx = 60 - len(pts)

                coords = []
                for i, val in enumerate(pts):
                    x = (start_idx + i) * x_step
                    y = max(2, min(h - 2, to_y(val)))
                    coords.append((x, y))

                cr.set_source_rgba(color[0], color[1], color[2], 0.95)
                cr.set_line_width(1.8)
                cr.move_to(coords[0][0], coords[0][1])
                for pt in coords[1:]:
                    cr.line_to(pt[0], pt[1])
                cr.stroke()

                last_x, last_y = coords[-1]
                cr.arc(last_x, last_y, 3.5, 0, 2 * 3.14159)
                cr.fill()

        return True
