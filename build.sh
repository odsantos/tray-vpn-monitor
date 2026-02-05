#!/bin/bash

# 0. Ensure we are in the script's actual directory
cd "$(dirname "$0")"

# Unified Name
APP_NAME="tray-vpn-monitor"
ICON_DIR="$HOME/.local/share/icons"
ICON_PATH="$ICON_DIR/vpn_monitor_icon.png"
APP_DIR="$HOME/.local/share/applications"
VENV_DIR=".venv"

echo "--- Initializing Build for $APP_NAME ---"

# 1. Cleanup old build artifacts
rm -rf build/ dist/ "$APP_NAME" "$APP_NAME.spec"

# 2. Virtual Environment Detection & Validation
USE_EXISTING_VENV=false
VENV_PYTHON="./$VENV_DIR/bin/python3"
VENV_PIP="./$VENV_DIR/bin/pip"

if [ -d "$VENV_DIR" ]; then
    # Check if the python binary exists and is executable
    if [ -x "$VENV_PYTHON" ]; then
        # Check if essential packages are already installed to avoid unnecessary pip/network calls
        if "$VENV_PYTHON" -c "import PyQt6, PyInstaller" 2>/dev/null; then
            echo "Found healthy virtual environment with dependencies. Skipping setup..."
            USE_EXISTING_VENV=true
        else
            echo "Virtual environment exists but is missing dependencies."
            USE_EXISTING_VENV=true 
        fi
    else
        echo "Detected broken .venv directory. Re-initializing..."
        rm -rf "$VENV_DIR"
    fi
fi

# 3. Virtual Environment Setup (only if needed or for updates)
if [ "$USE_EXISTING_VENV" = false ]; then
    echo "Creating fresh virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Installing dependencies..."
    $VENV_PIP install --upgrade pip
    $VENV_PIP install PyQt6 PyInstaller
else
    # Check for connectivity before attempting an update to prevent hanging/errors
    echo "Checking internet connectivity for potential updates..."
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        echo "Internet detected. Ensuring dependencies are up to date..."
        $VENV_PIP install -q PyQt6 PyInstaller
    else
        echo "No internet connection. Using existing packages in .venv..."
    fi
fi

# 4. Icon Generation
# This uses the venv python to ensure PyQt6 is available for the generation script
mkdir -p "$ICON_DIR"
echo "Generating application icon..."
$VENV_PYTHON -c "
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPolygon
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv); pixmap = QPixmap(256, 256); pixmap.fill(QColor(0, 0, 0, 0))
painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor('#4285F4')); painter.drawRect(40, 40, 48, 176)
painter.setBrush(QColor('#FBBC05')); painter.drawRect(168, 40, 48, 176)
painter.setBrush(QColor('#34A853')); painter.drawPolygon(QPolygon([QPoint(40, 40), QPoint(88, 40), QPoint(216, 216), QPoint(168, 216)]))
painter.end(); pixmap.save('$ICON_PATH')
"

# 5. Build with PyInstaller
echo "Compiling binary..."
$VENV_PYTHON -m PyInstaller --noconfirm --onefile --windowed --name "$APP_NAME" --clean main.py

# 6. Deployment (Moving binary out of dist/ and cleaning up)
if [ -f "dist/$APP_NAME" ]; then
    # Move binary to root as per instructions
    mv "dist/$APP_NAME" .
    echo "$APP_NAME" > .hidden
    
    DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=VPN Monitor
Comment=Monitor VPN status in the system tray
Exec=$(pwd)/$APP_NAME
Icon=$ICON_PATH
Terminal=false
Categories=Network;Utility;
X-GNOME-Autostart-enabled=true"

    # Install desktop entry
    echo "$DESKTOP_CONTENT" > "$APP_DIR/$APP_NAME.desktop"
    echo "$DESKTOP_CONTENT" > "$APP_NAME.desktop"
    
    chmod +x "$APP_NAME" "$APP_NAME.desktop"
    
    # Final Cleanup: No 'dist' or 'build' folders should remain
    rm -rf build/ dist/ "$APP_NAME.spec"
    
    # Get Absolute Paths
    ABS_BINARY_DIR="$(pwd)"
    ABS_APP_DIR="$APP_DIR"

    echo "--- SUCCESS! ---"
    echo "Binary located in: file://$ABS_BINARY_DIR"
    echo "Desktop file created in: file://$ABS_APP_DIR"
else
    echo "ERROR: Build failed. Check current directory for main.py"
    exit 1
fi