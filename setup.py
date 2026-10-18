from setuptools import setup, find_packages

setup(
    name="power-monitor",
    version="1.0.0",
    description="Universal Hardware Power & Voltage Telemetry Monitor with Desktop Panel Indicator",
    long_description=open("README.md").read() if open("README.md") else "",
    long_description_content_type="text/markdown",
    author="Beno Labs",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],
    entry_points={
        "console_scripts": [
            "power-monitor = power_monitor.main:main",
        ],
    },
    data_files=[
        ("share/applications", ["data/power-monitor.desktop"]),
        ("share/icons/hicolor/scalable/apps", ["data/icons/power-monitor.svg"]),
    ],
    classifiers=[
        "Environment :: X11 Applications :: GTK",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Hardware :: Hardware Monitoring",
    ],
)
