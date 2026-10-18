.PHONY: all run indicator status daemon clean deb ppa install help

PYTHON := /usr/bin/python3

all: help

help:
	@echo "Hardware Power & Voltage Monitor - Build & Run Helper"
	@echo "------------------------------------------------------"
	@echo "  make run        : Launch the GTK3 GUI and top-panel indicator"
	@echo "  make indicator  : Launch only the top-panel indicator (minimized)"
	@echo "  make daemon     : Run headless background daemon (logs to journald)"
	@echo "  make status     : Print one-shot hardware telemetry snapshot to console"
	@echo "  make deb        : Build local Debian (.deb) package with dpkg-deb"
	@echo "  make ppa        : Build signed source package for Ubuntu Launchpad PPA"
	@echo "  make clean      : Remove build artifacts and temporary files"
	@echo "  make install    : Install locally via pip/setuptools"

run:
	$(PYTHON) power_monitor/main.py

indicator:
	$(PYTHON) power_monitor/main.py --no-gui

daemon:
	$(PYTHON) power_monitor/main.py --daemon

status:
	$(PYTHON) power_monitor/main.py --status

deb: clean
	@bash scripts/build_deb.sh

ppa: clean
	debuild -S -sa

clean:
	rm -rf build/ dist/ *.egg-info .pybuild/ debian/.debhelper/ debian/debhelper-build-stamp debian/files debian/power-monitor/ debian/power-monitor.substvars debian/*.log
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

install:
	pip install . --break-system-packages
