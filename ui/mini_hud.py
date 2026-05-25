"""Compact always-on-top HUD when main window is hidden or during tool work."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_STYLE = """
QWidget#hud_root {
    background: rgba(0, 6, 18, 230);
    border: 1px solid #00d4ff;
    border-radius: 10px;
}
QLabel  { color: #00d4ff; border: none; background: transparent; }
QPushButton {
    color: #00d4ff;
    background: rgba(0,212,255,18);
    border: 1px solid rgba(0,212,255,60);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 10px;
    font-family: 'Courier New';
}
QPushButton:hover  { background: rgba(0,212,255,40); }
QPushButton#stop   { color: #ff4444; border-color: rgba(255,60,60,80); }
QPushButton#stop:hover { background: rgba(255,60,60,40); }
QPushButton#restore { color: #00ff88; border-color: rgba(0,255,136,80); }
"""

_STATE_COLORS = {
    "LISTENING": "#00ff88",
    "THINKING": "#ffaa00",
    "PROCESSING": "#ff6600",
    "SPEAKING": "#00d4ff",
    "IDLE": "#335566",
    "MUTED": "#886644",
}


class MiniHUD(QWidget):
    send_command = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S")
        self.setFixedSize(310, 145)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        self._position_br()
        self._blink = QTimer(self)
        self._blink.setInterval(600)
        self._blink.timeout.connect(self._do_blink)
        self._blink_on = True

    def _build_ui(self):
        self.setStyleSheet(_STYLE)
        root = QWidget(self)
        root.setObjectName("hud_root")
        root.setGeometry(0, 0, 310, 145)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)

        hdr = QHBoxLayout()
        title = QLabel("⬡  J.A.R.V.I.S")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        hdr.addWidget(title)
        hdr.addStretch()
        restore = QPushButton("↗ OPEN")
        restore.setObjectName("restore")
        restore.setFixedHeight(22)
        restore.clicked.connect(lambda: self.send_command.emit("__restore_main__"))
        hdr.addWidget(restore)
        lay.addLayout(hdr)

        self._state_lbl = QLabel("● LISTENING")
        self._state_lbl.setFont(QFont("Courier New", 8))
        lay.addWidget(self._state_lbl)

        self._text_lbl = QLabel("Ready, SS.")
        self._text_lbl.setFont(QFont("Segoe UI", 8))
        self._text_lbl.setStyleSheet("color: #7ecfdf; border: none;")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setMaximumHeight(34)
        lay.addWidget(self._text_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        stop_btn = QPushButton("⏹ STOP")
        stop_btn.setObjectName("stop")
        stop_btn.setFixedHeight(24)
        stop_btn.clicked.connect(lambda: self.send_command.emit("stop"))
        btn_row.addWidget(stop_btn)
        for label, cmd in [("Tasks", "list tasks"), ("Weather", "pull weather")]:
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.clicked.connect(lambda _, c=cmd: self.send_command.emit(c))
            btn_row.addWidget(b)
        screen_btn = QPushButton("🖥 Screen")
        screen_btn.setFixedHeight(24)
        screen_btn.clicked.connect(lambda: self.send_command.emit("view my screen"))
        btn_row.addWidget(screen_btn)
        lay.addLayout(btn_row)

    def _position_br(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 330, screen.height() - 200)

    def set_state(self, state: str):
        color = _STATE_COLORS.get(state, "#00d4ff")
        self._state_lbl.setText(f"● {state}")
        self._state_lbl.setStyleSheet(f"color: {color}; border: none;")
        if state in ("PROCESSING", "THINKING"):
            self._blink.start()
        else:
            self._blink.stop()
            self._state_lbl.setVisible(True)

    def _do_blink(self):
        self._blink_on = not self._blink_on
        self._state_lbl.setVisible(self._blink_on)

    def set_text(self, text: str):
        self._text_lbl.setText((text or "")[:130])


_instance: MiniHUD | None = None


def get_mini_hud() -> MiniHUD:
    global _instance
    if _instance is None:
        if QApplication.instance() is None:
            raise RuntimeError("QApplication must exist before MiniHUD")
        _instance = MiniHUD()
    return _instance
