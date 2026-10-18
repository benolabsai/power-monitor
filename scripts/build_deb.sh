#!/bin/bash
set -e

VERSION="1.0.1"
PKG_DIR="build/deb_staging"

echo "==> Preparing Debian package staging directory..."
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/lib/python3/dist-packages/power_monitor"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${PKG_DIR}/lib/systemd/system"
mkdir -p "${PKG_DIR}/lib/udev/rules.d"

# 1. Copy Python application files
cp -r power_monitor/*.py "${PKG_DIR}/usr/lib/python3/dist-packages/power_monitor/"

# 2. Executable launcher
cat << 'LAUNCHER' > "${PKG_DIR}/usr/bin/power-monitor"
#!/bin/sh
exec python3 -m power_monitor.main "$@"
LAUNCHER
chmod 755 "${PKG_DIR}/usr/bin/power-monitor"

# 3. Desktop, Icon, Systemd, and udev assets
cp data/power-monitor.desktop "${PKG_DIR}/usr/share/applications/"
cp data/icons/power-monitor.svg "${PKG_DIR}/usr/share/icons/hicolor/scalable/apps/"
cp data/power-monitor.service "${PKG_DIR}/lib/systemd/system/"
cp data/99-power-monitor-rapl.rules "${PKG_DIR}/lib/udev/rules.d/"

# 4. DEBIAN/control
cat << 'CTRL' > "${PKG_DIR}/DEBIAN/control"
Package: power-monitor
Version: 1.0.1-1
Section: utils
Priority: optional
Architecture: all
Maintainer: Beno Labs <rla3rd@gmail.com>
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, python3-cairo, lm-sensors
Description: Hardware Power & Voltage Telemetry Monitor with Desktop Panel Indicator
 Real-time hardware telemetry tool for PC builders, overclockers, and multi-GPU
 workstations. Includes live ATX +12V rail monitoring, CPU Package power, GPU
 wattage telemetry, Ayatana top-panel indicator, and native systemd-journald logging.
CTRL

# 5. DEBIAN/postinst
cat << 'POSTINST' > "${PKG_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
fi
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=powercap || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
POSTINST
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# 6. Build .deb package via dpkg-deb
mkdir -p dist
dpkg-deb --build --root-owner-group "${PKG_DIR}" "dist/power-monitor_${VERSION}-1_all.deb"
echo "==> Successfully created: dist/power-monitor_${VERSION}-1_all.deb"
