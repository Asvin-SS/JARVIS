from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime

import psutil
import requests

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut, QIcon, QAction,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar, QSystemTrayIcon, QMenu,
    QRadioButton, QButtonGroup, QGridLayout,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1100, 750
_MIN_W,     _MIN_H     = 900, 650
_LEFT_W  = 148

_OS = platform.system()


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now
        gpu = self._get_gpu()
        tmp = self._get_temp()
        with self._lock:
            self.cpu = cpu; self.mem = mem; self.net = net; self.gpu = gpu; self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1)
            if r.returncode == 0: return float(r.stdout.strip())
        except Exception: pass
        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "cpu_thermal", "acpitz"]:
                if name in temps and temps[name]: return temps[name][0].current
        except Exception: pass
        return -1.0

    def snapshot(self):
        with self._lock:
            return {"cpu": self.cpu, "mem": self.mem, "net": self.net, "gpu": self.gpu, "tmp": self.tmp}

_metrics = _SysMetrics()

class MetricBar(QWidget):
    def __init__(self, label: str, color: str):
        super().__init__()
        self.label = label
        self.color = qcol(color)
        self.val   = 0.0
        self.txt   = "--"
        self.setFixedHeight(34)

    def set_value(self, v: float, t: str):
        self.val = v; self.txt = t; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(qcol(C.BORDER), 1)); p.setBrush(qcol(C.PANEL2))
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 3, 3)
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(qcol(C.TEXT_DIM)); p.drawText(6, 12, self.label)
        p.setPen(qcol(C.WHITE)); p.drawText(self.width()-40, 12, self.txt)
        bar_w = self.width() - 12
        p.setBrush(qcol(C.PRI_GHO)); p.drawRect(6, 18, bar_w, 4)
        fill = int(bar_w * (min(100, self.val)/100.0))
        if fill > 0:
            p.setBrush(self.color); p.drawRect(6, 18, fill, 4)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFrameStyle(0)
        self.setStyleSheet(f"background: transparent; color: {C.TEXT}; border: none;")
        self.setFont(QFont("Courier New", 9))
        self._sig.connect(self._enqueue)

    def append_log(self, text: str): self._sig.emit(text)

    def append_log_no_type(self, text: str):
        cur = self.textCursor(); cur.movePosition(cur.MoveOperation.End)
        fmt = cur.charFormat()
        tl = text.lower()
        if tl.startswith("you:"): col = qcol(C.WHITE)
        elif tl.startswith("jarvis:"): col = qcol(C.PRI)
        elif tl.startswith("file:"): col = qcol(C.GREEN)
        elif "err" in tl: col = qcol(C.RED)
        else: col = qcol(C.ACC2)
        fmt.setForeground(QBrush(col))
        cur.insertText(text, fmt); self.setTextCursor(cur); self.ensureCursorVisible()

    def stream_chunk(self, chunk: str):
        cur = self.textCursor(); cur.movePosition(cur.MoveOperation.End)
        fmt = cur.charFormat(); fmt.setForeground(QBrush(qcol(C.PRI)))
        cur.insertText(chunk, fmt); self.setTextCursor(cur); self.ensureCursorVisible()

    def _enqueue(self, text: str):
        self.append_log_no_type(text + "\n")

class FileDropZone(QFrame):
    file_selected = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFixedHeight(60)
        self.setStyleSheet(f"QFrame {{ border: 2px dashed {C.BORDER}; border-radius: 8px; background: {C.PANEL2}; }}")
        lay = QVBoxLayout(self); self.lbl = QLabel("Drop files here or click to upload"); self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setFont(QFont("Courier New", 8)); self.lbl.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;"); lay.addWidget(self.lbl)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls: self.file_selected.emit(urls[0].toLocalFile())

    def mousePressEvent(self, _):
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path: self.file_selected.emit(path)

class HudCanvas(QWidget):
    def __init__(self, face_path: str):
        super().__init__()
        self.face = QPixmap(face_path) if os.path.exists(face_path) else None
        self.state = "LISTENING"
        self.speaking = False
        self.muted = False
        self._rot = 0.0
        self._pulse = 0.0
        self._t = 0.0
        self._tmr = QTimer(self); self._tmr.timeout.connect(self._anim); self._tmr.start(30)

    def _anim(self):
        self._t += 0.05; self._rot += 1.0; self._pulse = math.sin(self._t) * 0.5 + 0.5; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r_base = min(cx, cy) * 0.7
        
        # Outer Ring
        p.setPen(QPen(qcol(C.PRI, 50), 2))
        p.drawEllipse(QPointF(cx, cy), r_base + 10, r_base + 10)
        
        # Rotating Arc
        p.setPen(QPen(qcol(C.PRI, 180), 3))
        p.drawArc(QRectF(cx-r_base, cy-r_base, r_base*2, r_base*2), int(self._rot*16), 120*16)
        
        # Inner Pulse
        color = qcol(C.PRI)
        if self.state == "THINKING": color = qcol(C.ACC2)
        elif self.state == "SPEAKING": color = qcol(C.GREEN)
        elif self.muted: color = qcol(C.RED)
        
        p.setBrush(QBrush(color, int(50 + self._pulse * 100)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r_base * 0.3, r_base * 0.3)
        
        if self.face:
            fw, fh = 120, 120
            p.drawPixmap(int(cx - fw/2), int(cy - fh/2), fw, fh, self.face)

class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _log_no_type_sig = pyqtSignal(str)
    _stream_sig = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("Mark-3.9")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)
        self._setup_tray()
        
        self.on_text_command = None
        self.on_close = None
        self.on_mute_changed = None
        self.muted = False
        
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        
        # Header
        header = QFrame(); header.setFixedHeight(60); header.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        h_lay = QHBoxLayout(header); h_lay.setContentsMargins(20, 0, 20, 0)
        
        title_v = QVBoxLayout(); title_v.setSpacing(0)
        t_lbl = QLabel("MARK-3.9"); t_lbl.setFont(QFont("Courier New", 16, QFont.Weight.Bold)); t_lbl.setStyleSheet(f"color: {C.PRI}; border: none;")
        s_lbl = QLabel("A product of SS"); s_lbl.setFont(QFont("Courier New", 7)); s_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;")
        title_v.addWidget(t_lbl); title_v.addWidget(s_lbl); h_lay.addLayout(title_v)
        
        h_lay.addStretch()
        
        self.clock = QLabel("00:00:00"); self.clock.setFont(QFont("Courier New", 18, QFont.Weight.Bold)); self.clock.setStyleSheet(f"color: {C.PRI}; border: none;")
        h_lay.addWidget(self.clock); h_lay.addStretch()
        
        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        self.mute_btn = QPushButton("🔊"); self.mute_btn.setFixedSize(36, 36); self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {C.BORDER}; border-radius: 4px; font-size: 14pt; }}")
        self.mute_btn.clicked.connect(self._toggle_mute)
        btn_row.addWidget(self.mute_btn)
        
        mod_btn = QPushButton("⚙ MODELS"); mod_btn.setFixedHeight(30); mod_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold)); mod_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mod_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}")
        mod_btn.clicked.connect(self._open_models)
        btn_row.addWidget(mod_btn)
        h_lay.addLayout(btn_row)
        root.addWidget(header)
        
        # Body
        body = QWidget(); body_lay = QHBoxLayout(body); body_lay.setContentsMargins(0, 0, 0, 0); body_lay.setSpacing(0)
        
        # Left Panel (Metrics)
        left_p = QFrame(); left_p.setFixedWidth(_LEFT_W); left_p.setStyleSheet(f"background: {C.PANEL}; border-right: 1px solid {C.BORDER};")
        lp_lay = QVBoxLayout(left_p); lp_lay.setContentsMargins(10, 15, 10, 15); lp_lay.setSpacing(8)
        self._b_cpu = MetricBar("CPU", C.PRI); self._b_mem = MetricBar("RAM", C.ACC2); self._b_net = MetricBar("NET", C.GREEN)
        self._b_gpu = MetricBar("GPU", C.ACC); self._b_tmp = MetricBar("TMP", C.RED)
        for b in [self._b_cpu, self._b_mem, self._b_net, self._b_gpu, self._b_tmp]: lp_lay.addWidget(b)
        lp_lay.addStretch()
        body_lay.addWidget(left_p)
        
        # Main Area (HUD + Chat)
        main_v = QVBoxLayout(); main_v.setContentsMargins(0, 0, 0, 0); main_v.setSpacing(0)
        self.hud = HudCanvas(face_path); main_v.addWidget(self.hud, stretch=3)
        
        chat_w = QFrame(); chat_w.setFixedHeight(260); chat_w.setStyleSheet(f"background: {C.PANEL2}; border-top: 1px solid {C.BORDER};")
        chat_lay = QVBoxLayout(chat_w); chat_lay.setContentsMargins(15, 10, 15, 10); chat_lay.setSpacing(8)
        self._log = LogWidget(); chat_lay.addWidget(self._log)
        
        self.drop = FileDropZone(); chat_lay.addWidget(self.drop)
        
        in_row = QHBoxLayout(); in_row.setSpacing(10)
        self.inp = QLineEdit(); self.inp.setFixedHeight(40); self.inp.setPlaceholderText("Message Jarvis..."); self.inp.setFont(QFont("Courier New", 10))
        self.inp.setStyleSheet(f"QLineEdit {{ background: {C.DARK}; color: {C.WHITE}; border: 1px solid {C.BORDER}; border-radius: 5px; padding: 0 12px; }}")
        self.inp.returnPressed.connect(self._send); in_row.addWidget(self.inp)
        
        s_btn = QPushButton("▸"); s_btn.setFixedSize(40, 40); s_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        s_btn.setStyleSheet(f"QPushButton {{ background: {C.PRI}; color: {C.BG}; border-radius: 5px; font-size: 16pt; font-weight: bold; }}")
        s_btn.clicked.connect(self._send); in_row.addWidget(s_btn)
        chat_lay.addLayout(in_row)
        main_v.addWidget(chat_w)
        body_lay.addLayout(main_v, stretch=1)
        
        # Right Side Panel (Task 8)
        self.side = QFrame(); self.side.setFixedWidth(280); self.side.setStyleSheet(f"background: {C.PANEL}; border-left: 1px solid {C.BORDER};")
        self.side_lay = QVBoxLayout(self.side); self.side_lay.setContentsMargins(12, 15, 12, 15); self.side_lay.setSpacing(15)
        
        # Jarvis Status Section
        s_card = self._sec_card("🤖 JARVIS STATUS")
        self.lbl_status = QLabel("● mistral:latest (Ollama)"); self.lbl_status.setFont(QFont("Courier New", 8)); self.lbl_status.setStyleSheet(f"color: {C.GREEN}; border: none;")
        s_card.layout().addWidget(self.lbl_status); self.side_lay.addWidget(s_card)
        
        # Tasks Section
        t_card = self._sec_card("📋 ACTIVE TASKS")
        self.lbl_tasks = QLabel("No active tasks."); self.lbl_tasks.setFont(QFont("Courier New", 8)); self.lbl_tasks.setWordWrap(True); self.lbl_tasks.setStyleSheet("color: #8ffcff; border: none;")
        t_card.layout().addWidget(self.lbl_tasks); self.side_lay.addWidget(t_card)
        
        # Watchlist Section
        w_card = self._sec_card("📈 WATCHLIST")
        self.lbl_watch = QLabel("Watchlist empty."); self.lbl_watch.setFont(QFont("Courier New", 8)); self.lbl_watch.setWordWrap(True); self.lbl_watch.setStyleSheet("color: #8ffcff; border: none;")
        w_card.layout().addWidget(self.lbl_watch); self.side_lay.addWidget(w_card)
        
        # Smart Home Section (Task 9)
        sh_card = self._sec_card("🏠 SMART HOME")
        self.lbl_sh = QLabel("Not connected."); self.lbl_sh.setFont(QFont("Courier New", 8)); self.lbl_sh.setWordWrap(True); self.lbl_sh.setStyleSheet("color: #8ffcff; border: none;")
        sh_card.layout().addWidget(self.lbl_sh); self.side_lay.addWidget(sh_card)
        
        # Weather Section
        we_card = self._sec_card("🌤 WEATHER")
        self.lbl_weather = QLabel("Loading..."); self.lbl_weather.setFont(QFont("Courier New", 8)); self.lbl_weather.setStyleSheet("color: #8ffcff; border: none;")
        we_card.layout().addWidget(self.lbl_weather); self.side_lay.addWidget(we_card)
        
        self.side_lay.addStretch()
        body_lay.addWidget(self.side)
        
        # Toggle button
        self.toggle = QPushButton(">"); self.toggle.setFixedSize(20, 50); self.toggle.setCursor(Qt.CursorShape.PointingHandCursor); self.toggle.setParent(self)
        self.toggle.setStyleSheet(f"QPushButton {{ background: {C.PANEL}; color: {C.PRI}; border: 1px solid {C.BORDER}; border-right: none; border-top-left-radius: 5px; border-bottom-left-radius: 5px; }}")
        self.toggle.clicked.connect(self._toggle_side)
        
        root.addWidget(body)
        
        # Timers
        self.t_clock = QTimer(self); self.t_clock.timeout.connect(self._tick); self.t_clock.start(1000)
        self.t_metric = QTimer(self); self.t_metric.timeout.connect(self._up_metrics); self.t_metric.start(2000)
        self.t_refresh = QTimer(self); self.t_refresh.timeout.connect(self._refresh_side); self.t_refresh.start(15000) # Every 15s for smart home/tasks
        
        self._log_sig.connect(self._log.append_log)
        self._log_no_type_sig.connect(self._log.append_log_no_type)
        self._stream_sig.connect(self._log.stream_chunk)
        self._state_sig.connect(self._apply_state)

    def _sec_card(self, title: str) -> QFrame:
        f = QFrame(); f.setStyleSheet(f"QFrame {{ background: {C.DARK}; border: 1px solid {C.BORDER}; border-radius: 4px; }}")
        l = QVBoxLayout(f); l.setContentsMargins(8, 8, 8, 8); l.setSpacing(5)
        t = QLabel(title); t.setFont(QFont("Courier New", 8, QFont.Weight.Bold)); t.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;"); l.addWidget(t)
        return f

    def _toggle_side(self):
        if self.side.isVisible(): self.side.hide(); self.toggle.setText("<")
        else: self.side.show(); self.toggle.setText(">")
        self._up_toggle()

    def _up_toggle(self):
        x = self.width() - (self.side.width() if self.side.isVisible() else 0) - self.toggle.width()
        self.toggle.move(x, (self.height() - self.toggle.height()) // 2)

    def resizeEvent(self, _): self._up_toggle()

    def _tick(self): self.clock.setText(time.strftime("%H:%M:%S"))

    def _up_metrics(self):
        s = _metrics.snapshot()
        self._b_cpu.set_value(s["cpu"], f"{s['cpu']:.0f}%")
        self._b_mem.set_value(s["mem"], f"{s['mem']:.0f}%")
        self._b_net.set_value(min(100, s["net"]*10), f"{s['net']:.1f}MB/s")
        self._b_gpu.set_value(s["gpu"] if s["gpu"]>=0 else 0, f"{s['gpu']:.0f}%" if s["gpu"]>=0 else "N/A")
        self._b_tmp.set_value(min(100, s["tmp"]) if s["tmp"]>=0 else 0, f"{s['tmp']:.0f}°C" if s["tmp"]>=0 else "N/A")

    def _refresh_side(self):
        threading.Thread(target=self._refresh_async, daemon=True).start()

    def _refresh_async(self):
        try:
            from db.database import get_active_tasks, get_watchlist
            tasks = get_active_tasks()
            watch = get_watchlist()
            t_txt = "\n".join([f"• {t['title']}" for t in tasks[:3]]) if tasks else "No active tasks."
            w_txt = "\n".join([f"• {w['symbol']}" for w in watch[:3]]) if watch else "Watchlist empty."
            
            # Weather and Smart Home would normally call their respective APIs here
            QTimer.singleShot(0, lambda: self.lbl_tasks.setText(t_txt))
            QTimer.singleShot(0, lambda: self.lbl_watch.setText(w_txt))
        except Exception: pass

    def _toggle_mute(self):
        self.muted = not self.muted; self.hud.muted = self.muted
        self.mute_btn.setText("🔇" if self.muted else "🔊")
        if self.on_mute_changed: self.on_mute_changed(self.muted)

    def _open_models(self):
        from ui_model_manager import ModelManagerDialog
        ModelManagerDialog(self).exec()

    def _send(self):
        t = self.inp.text().strip(); if not t: return
        self.inp.clear(); self._log.append_log(f"You: {t}")
        if self.on_text_command: self.on_text_command(t)

    def _apply_state(self, s: str):
        self.hud.state = s; self.hud.speaking = (s == "SPEAKING"); self.update()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        if os.path.exists(str(BASE_DIR / "face.png")): self.tray.setIcon(QIcon(str(BASE_DIR / "face.png")))
        m = QMenu(); m.addAction("Show").triggered.connect(self.show)
        m.addAction("Hide").triggered.connect(self.hide)
        m.addSeparator(); m.addAction("Quit").triggered.connect(QApplication.instance().quit)
        self.tray.setContextMenu(m); self.tray.show()

    def closeEvent(self, e):
        if self.tray.isVisible():
            self.hide(); if self.on_close: self.on_close()
            e.ignore()
        else: e.accept()

class JarvisUI:
    def __init__(self, face_path: str):
        self._win = MainWindow(face_path)
        self.state = "IDLE"
        self.current_file = None
        self._win.drop.file_selected.connect(self._on_file)

    @property
    def on_text_command(self): return self._win.on_text_command
    @on_text_command.setter
    def on_text_command(self, cb): self._win.on_text_command = cb

    @property
    def on_mute_changed(self): return self._win.on_mute_changed
    @on_mute_changed.setter
    def on_mute_changed(self, cb): self._win.on_mute_changed = cb

    @property
    def on_close(self): return self._win.on_close
    @on_close.setter
    def on_close(self, cb): self._win.on_close = cb

    def show(self): self._win.show()
    def write_log(self, t: str): self._win._log_sig.emit(t)
    def write_log_no_type(self, t: str): self._win._log_no_type_sig.emit(t)
    def stream_chunk(self, c: str): self._win._stream_sig.emit(c)
    def set_state(self, s: str): self.state = s; self._win._state_sig.emit(s)
    def set_muted(self, m: bool): self._win.muted = m; self._win.mute_btn.setText("🔇" if m else "🔊")

    def _on_file(self, p: str):
        self.current_file = p; self.write_log(f"FILE: Loaded {Path(p).name}")
