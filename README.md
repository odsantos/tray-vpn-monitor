# Tray VPN Monitor

A system tray application built with PyQt6 to monitor VPN status on Linux.

## Features

* Real-time system tray icon updates.
* Automatic build script for Linux.
* Auto-generates high-quality application icons.
* Creates a `.desktop` entry for easy application launching.

## Installation & Building

### Option 1: Build Standalone Binary (Recommended)

To build the application and install the desktop shortcut, run:

```bash
chmod +x build.sh
./build.sh
```

The script will:

1. Set up a virtual environment (`.venv`).
2. Install dependencies (`PyQt6`, `PyInstaller`).
3. Generate the application icon automatically.
4. Compile the app into a single standalone binary in the root directory.

### Option 2: Install as Python Package

```bash
pip install .
```

## Usage

Once built, you can launch the app in two ways:

1. **Desktop Menu**: Search for "VPN Monitor" in your application launcher.
2. **Terminal**: Run `./tray-vpn-monitor` from the project root.

## Credits

Developed by **Osvaldo Santos** in collaboration with **Gemini AI**.

## Requirements

- Python 3.x
- Bash (Linux)
