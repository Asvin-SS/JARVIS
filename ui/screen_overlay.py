"""Live screen preview overlay — drag to move, resize grip, auto-refresh."""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QObject
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget, QSizeGrip,
)

_STYLE = """
QWidget#overlay_root {
    background: #00060a;
    border: 1px solid #00d4ff;
    border-radius: 8px;
}
QLabel  { color: #00d4ff; border: none; background: transparent; }
QPushButton {
    color: #00d4ff; background: rgba(0,212,255,15);
    border: 1px solid rgba(0,212,255,50); border-radius: 3px;
    padding: 2px 8px; font-size: 10px; font-family: Courier New;
}
QPushButton:hover { background: rgba(0,212,255,40); }
QPushButton#close_btn { color: #ff6666; border-color: rgba(255,80,80,60); }
"""


class _Relay(QObject):
    """Lives on the main thread — receives bytes from capture thread, updates UI."""
    update_frame = pyqtSignal(bytes)


class ScreenPreviewOverlay(QWidget):
    closed = pyqtSignal()

    def __init__(self, refresh_sec: int = 10):
        super().__init__()
        self._refresh_sec = refresh_sec
        self._drag_pos = QPoint()
        self._capturing = False
        self._relay = _Relay()
        self._relay.update_frame.connect(self._set_pixmap_bytes)

        self.setWindowTitle("Screen")
        self.setMinimumSize(240, 180)
        self.resize(340, 260)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        self._position_tl()

        self._timer = QTimer(self)
        self._timer.setInterval(refresh_sec * 1000)
        self._timer.timeout.connect(self._capture_async)

    def _build_ui(self):
        self.setStyleSheet(_STYLE)
        self._root = QWidget(self)
        self._root.setObjectName("overlay_root")
        self._root.setGeometry(0, 0, self.width(), self.height())

        lay = QVBoxLayout(self._root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        hdr = QHBoxLayout()
        title = QLabel("👁  SCREEN VISION")
        title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        hdr.addWidget(title)
        hdr.addStretch()

        self._ts_lbl = QLabel("LIVE")
        self._ts_lbl.setFont(QFont("Courier New", 7))
        self._ts_lbl.setStyleSheet("color: #00ff88; border: none;")
        hdr.addWidget(self._ts_lbl)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("close_btn")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self._close_overlay)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img = QLabel("Starting capture…")
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet(
            "background:#010d14; color:#5ab8cc;"
            "border:1px solid #0d3347; border-radius:4px;"
        )
        self._img.setMinimumHeight(140)
        lay.addWidget(self._img, 1)

        foot = QHBoxLayout()
        foot.setSpacing(4)
        for label, rate in [("5s", 5), ("15s", 15), ("30s", 30)]:
            b = QPushButton(label)
            b.setFixedHeight(20)
            b.clicked.connect(lambda _, r=rate: self._set_rate(r))
            foot.addWidget(b)
        self._pause_btn = QPushButton("⏸")
        self._pause_btn.setFixedHeight(20)
        self._pause_btn.clicked.connect(self._toggle_pause)
        foot.addWidget(self._pause_btn)
        foot.addStretch()
        foot.addWidget(QSizeGrip(self))
        lay.addLayout(foot)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_root"):
            self._root.setGeometry(0, 0, self.width(), self.height())

    def _position_tl(self):
        self.move(20, 60)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _capture_async(self):
        if self._capturing:
            return
        threading.Thread(target=self._do_capture, daemon=True).start()

    def _do_capture(self):
        self._capturing = True
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                png = mss.tools.to_png(shot.rgb, shot.size)
            self._relay.update_frame.emit(png)
        except Exception as e:
            print(f"[Overlay] Capture error: {e}")
        finally:
            self._capturing = False

    def _set_pixmap_bytes(self, png_bytes: bytes):
        px = QPixmap()
        if px.loadFromData(png_bytes):
            w = max(self._img.width(), 200)
            h = max(self._img.height(), 140)
            scaled = px.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img.setPixmap(scaled)
            self._ts_lbl.setText(time.strftime("%H:%M:%S"))

    def update_frame(self, png_bytes: bytes):
        self._relay.update_frame.emit(png_bytes)

    def _set_rate(self, seconds: int):
        self._refresh_sec = seconds
        self._timer.setInterval(seconds * 1000)
        self._ts_lbl.setText(f"Every {seconds}s")

    def _toggle_pause(self):
        if self._timer.isActive():
            self._timer.stop()
            self._pause_btn.setText("▶")
            self._ts_lbl.setText("PAUSED")
        else:
            self._timer.start()
            self._pause_btn.setText("⏸")

    def _close_overlay(self):
        self._timer.stop()
        self.hide()
        self.closed.emit()

    def show_active(self):
        self.show()
        self.raise_()
        threading.Thread(target=self._do_capture, daemon=True).start()
        self._timer.start()

    def hide(self):
        self._timer.stop()
        super().hide()


_instance: ScreenPreviewOverlay | None = None


def get_overlay() -> ScreenPreviewOverlay:
    global _instance
    if _instance is None:
        if QApplication.instance() is None:
            raise RuntimeError("QApplication must exist before overlay")
        _instance = ScreenPreviewOverlay(refresh_sec=10)
    return _instance


def show_screen_preview(png_bytes: bytes | None = None):
    try:
        ov = get_overlay()
        if png_bytes:
            ov.update_frame(png_bytes)
        ov.show_active()
    except Exception as e:
        print(f"[Overlay] Show error: {e}")


def hide_screen_preview():
    global _instance
    if _instance:
        _instance.hide()
