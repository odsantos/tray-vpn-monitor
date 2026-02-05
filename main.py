import sys
import os
import subprocess
import threading
import time
import urllib.request
from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QTextEdit, 
                             QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QPolygon
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QPoint, QTimer

class VPNWorker(QObject):
    status_changed = pyqtSignal(str)
    log_added = pyqtSignal(str)
    api_called = pyqtSignal(int)
    notification_requested = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.enabled = True
        self.monitor_process = None
        self.last_status = None
        self.is_resolving = False
        self.api_count = 0
        self._check_lock = threading.Lock()
        self._debounce_timer = None

    def start(self):
        self.log_added.emit("SYSTEM: Monitor initialized.")
        threading.Thread(target=self.perform_check, kwargs={'source': "Init"}, daemon=True).start()
        threading.Thread(target=self._listen, daemon=True).start()

    def _track_api(self):
        self.api_count += 1
        self.api_called.emit(self.api_count)

    def _get_public_ip(self):
        self.log_added.emit("API CALL: Fetching Public IP (icanhazip.com)")
        self._track_api()
        try:
            req = urllib.request.Request("https://icanhazip.com", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode('utf-8').strip()
        except Exception as e:
            self.log_added.emit(f"API ERROR: IP fetch failed: {e}")
            return None

    def _has_internet(self):
        self.log_added.emit("API CALL: Checking connectivity (google.com)")
        self._track_api()
        for i in range(1, 4):
            try:
                req = urllib.request.Request('http://www.google.com', headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3):
                    return True
            except:
                if i < 3: time.sleep(1.2)
        return False

    def _is_interface_active(self, iface):
        try:
            with open(f'/sys/class/net/{iface}/operstate', 'r') as f:
                return f.read().strip().lower() != "down"
        except: return False

    def _listen(self):
        def trigger_check():
            self.perform_check(source="Auto")

        try:
            self.monitor_process = subprocess.Popen(["nmcli", "monitor"], stdout=subprocess.PIPE, text=True)
            for line in self.monitor_process.stdout:
                if not self.enabled: continue
                line_clean = line.strip().lower()
                if any(word in line_clean for word in ["connected", "vpn", "connectivity", "disconnected", "removed", "unavailable"]):
                    if self._debounce_timer: self._debounce_timer.cancel()
                    if not self.is_resolving:
                        self.status_changed.emit('yellow')
                        self.is_resolving = True
                        self.last_status = None 
                    self._debounce_timer = threading.Timer(2.5, trigger_check)
                    self._debounce_timer.start()
        except Exception as e:
            self.log_added.emit(f"DEBUG: Monitor Error: {e}")

    def perform_check(self, source="Auto"):
        if not self.enabled: return
        with self._check_lock:
            if not self.is_resolving:
                self.status_changed.emit('yellow')
                self.is_resolving = True

            try:
                try:
                    interfaces = os.listdir('/sys/class/net/')
                except:
                    interfaces = []
                
                vpn_ifaces = [i for i in interfaces if i.startswith(('tun', 'wg', 'ppp'))]
                active_vpn = any(self._is_interface_active(iface) for iface in vpn_ifaces) if vpn_ifaces else False
                is_online = self._has_internet()
                
                if active_vpn and is_online:
                    current_status, label = 'green', "Protected"
                elif is_online:
                    current_status, label = 'blue', "Insecure"
                else:
                    current_status, label = 'red', "Offline"

                state_changed = (current_status != self.last_status)
                forced_check = (source in ["Init", "Manual", "Toggle"])

                if state_changed or self.is_resolving or forced_check:
                    self.last_status = current_status
                    self.is_resolving = False
                    self.status_changed.emit(current_status)
                    
                    ip_suffix = ""
                    if current_status == 'blue' or (source == "Manual" and is_online):
                        ip = self._get_public_ip()
                        if ip: ip_suffix = f" (IP: {ip})"
                    
                    self.log_added.emit(f"STATUS: {label} [{source}]{ip_suffix}")

                if current_status == 'blue' and (state_changed or forced_check):
                    threading.Timer(0.2, lambda: self.notification_requested.emit(
                        "⚠️ VPN DROPPED", "Traffic is now EXPOSED!", True
                    )).start()

            except Exception as e:
                self.log_added.emit(f"CRITICAL ERROR: {e}")
                self.is_resolving = False
                self.status_changed.emit('red')

    def cleanup(self):
        if self.monitor_process: self.monitor_process.terminate()

class VPNMonitorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.autostart_path = os.path.expanduser("~/.config/autostart/vpn-monitor.desktop")
        
        self.icons = self._generate_icons()
        self.app_icon = self._generate_app_icon()
        
        # Pulse Animation Setup
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._toggle_pulse)
        self.pulse_state = False

        self.worker = VPNWorker()
        self.worker.status_changed.connect(self.update_icon)
        self.worker.log_added.connect(self.add_to_log_window)
        self.worker.api_called.connect(self.update_api_counter)
        self.worker.notification_requested.connect(self.show_tray_message)
        
        self._setup_log_window()
        self._setup_tray()

    def _setup_log_window(self):
        self.log_window = QWidget()
        self.log_window.setWindowTitle("VPN Debug Logs")
        self.log_window.setWindowIcon(self.app_icon)
        self.log_window.resize(600, 500)
        layout = QVBoxLayout()
        self.text_area = QTextEdit(); self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: monospace;")
        layout.addWidget(self.text_area)
        stats_layout = QHBoxLayout()
        self.api_label = QLabel("Total API Calls: 0")
        self.api_label.setStyleSheet("color: #569cd6; font-weight: bold;")
        stats_layout.addWidget(self.api_label)
        stats_layout.addStretch()
        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.clicked.connect(lambda: self.text_area.clear())
        stats_layout.addWidget(self.clear_btn)
        layout.addLayout(stats_layout)
        self.log_window.setLayout(layout)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon()
        self.update_icon('yellow') # Start with yellow immediately
        self.menu = QMenu()

        help_menu = self.menu.addMenu("Status Key")
        help_menu.addAction("🟢 Green: VPN Protected")
        help_menu.addAction("🔵 Blue: Insecure (Online)")
        help_menu.addAction("🟡 Yellow (Pulsing): Verifying...")
        help_menu.addAction("🔴 Red: Offline")
        help_menu.addAction("⚪ Grey: Monitoring Disabled")
        help_menu.addSeparator()
        
        self.startup_act = QAction("Run at Startup", help_menu, checkable=True)
        self.startup_act.setChecked(os.path.exists(self.autostart_path))
        self.startup_act.triggered.connect(self.toggle_startup)
        help_menu.addAction(self.startup_act)

        self.menu.addSeparator()
        self.toggle_act = QAction("Disable Monitoring", self.tray)
        self.toggle_act.triggered.connect(self.toggle_monitoring)
        self.menu.addAction(self.toggle_act)
        self.menu.addAction("Check Now", lambda: threading.Thread(target=self.worker.perform_check, kwargs={'source': "Manual"}, daemon=True).start())
        self.menu.addSeparator()
        self.show_log_act = QAction(self.app_icon, "Show Debug Log", self.tray)
        self.show_log_act.triggered.connect(self.log_window.show)
        self.menu.addAction(self.show_log_act)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(self.menu); self.tray.show()

    def _generate_icons(self):
        icons = {}
        colors = {'blue': QColor(0, 122, 255), 'green': QColor(40, 167, 69), 
                  'yellow': QColor(255, 193, 7), 'yellow_alt': QColor(255, 193, 7, 100), # Lower Alpha
                  'red': QColor(220, 53, 69), 'grey': QColor(150, 150, 150)}
        for name, color in colors.items():
            pixmap = QPixmap(64, 64); pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = painter.pen(); pen.setColor(color); pen.setWidth(8); painter.setPen(pen)
            painter.drawLine(15, 15, 15, 49); painter.drawLine(15, 15, 49, 49); painter.drawLine(49, 49, 49, 15); painter.end()
            icons[name] = QIcon(pixmap)
        return icons

    def _generate_app_icon(self):
        pixmap = QPixmap(64, 64); pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4285F4")); painter.drawRect(10, 10, 12, 44)
        painter.setBrush(QColor("#FBBC05")); painter.drawRect(42, 10, 12, 44)
        painter.setBrush(QColor("#34A853")); painter.drawPolygon(QPolygon([QPoint(10, 10), QPoint(22, 10), QPoint(54, 54), QPoint(42, 54)]))
        painter.end(); return QIcon(pixmap)

    def _toggle_pulse(self):
        self.pulse_state = not self.pulse_state
        icon_key = 'yellow_alt' if self.pulse_state else 'yellow'
        self.tray.setIcon(self.icons[icon_key])

    def update_icon(self, status):
        if status == 'yellow':
            if not self.pulse_timer.isActive():
                self.pulse_timer.start(998) # Pulse every 998ms
        else:
            self.pulse_timer.stop()
            self.tray.setIcon(self.icons[status])

    def show_tray_message(self, title, message, critical):
        icon = QSystemTrayIcon.MessageIcon.Critical if critical else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(title, message, icon, 0 if critical else 3000)

    def toggle_monitoring(self):
        self.worker.enabled = not self.worker.enabled
        if self.worker.enabled:
            self.toggle_act.setText("Disable Monitoring")
            self.add_to_log_window("SYSTEM: Monitoring re-enabled.")
            threading.Thread(target=self.worker.perform_check, kwargs={'source': "Toggle"}, daemon=True).start()
        else:
            self.toggle_act.setText("Enable Monitoring")
            self.add_to_log_window("SYSTEM: Monitoring disabled.")
            self.update_icon('grey')

    def toggle_startup(self):
        if self.startup_act.isChecked():
            try:
                os.makedirs(os.path.dirname(self.autostart_path), exist_ok=True)
                with open(self.autostart_path, "w") as f:
                    f.write(f"[Desktop Entry]\nType=Application\nName=VPN Monitor\nExec={os.path.abspath(sys.argv[0])}\nHidden=false\nNoDisplay=false\nX-GNOME-Autostart-enabled=true\n")
                self.add_to_log_window("SYSTEM: Autostart enabled.")
            except Exception as e:
                self.add_to_log_window(f"ERROR: Could not create autostart: {e}")
        else:
            if os.path.exists(self.autostart_path):
                os.remove(self.autostart_path)
                self.add_to_log_window("SYSTEM: Autostart disabled.")

    def update_api_counter(self, count): self.api_label.setText(f"Total API Calls: {count}")
    def add_to_log_window(self, msg): self.text_area.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    def quit_app(self): self.worker.cleanup(); self.app.quit()
    def run(self): self.worker.start(); sys.exit(self.app.exec())

if __name__ == "__main__":
    VPNMonitorApp().run()