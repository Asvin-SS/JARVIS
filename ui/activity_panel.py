"""Right-side mini panel — shows active tool/agent work (Teams-meet style)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

_PANEL_WIDTH = 220
_PANEL = None


class ActivitySidePanel(QFrame):
    """Collapsible side strip showing live tool execution."""

    _sig_start = pyqtSignal(str, str)
    _sig_line = pyqtSignal(str)
    _sig_end = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_PANEL_WIDTH)
        self.setStyleSheet(
            "background: #000810; border-left: 1px solid #0d3347;"
        )
        self._visible = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(4)

        hdr = QLabel("⚡ AGENT TASK")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #00d4ff; background: transparent; border: none;")
        lay.addWidget(hdr)

        self._tool_lbl = QLabel("Idle")
        self._tool_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._tool_lbl.setWordWrap(True)
        self._tool_lbl.setStyleSheet("color: #7ec8e3; background: transparent; border: none;")
        lay.addWidget(self._tool_lbl)

        self._detail_lbl = QLabel("")
        self._detail_lbl.setFont(QFont("Courier New", 7))
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet("color: #5ab8cc; background: transparent; border: none;")
        lay.addWidget(self._detail_lbl)

        self._log_lbl = QLabel("")
        self._log_lbl.setFont(QFont("Courier New", 7))
        self._log_lbl.setWordWrap(True)
        self._log_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._log_lbl.setStyleSheet("color: #8899aa; background: transparent; border: none;")
        lay.addWidget(self._log_lbl, stretch=1)

        self._pulse = QLabel("● RUNNING")
        self._pulse.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._pulse.setStyleSheet("color: #44ff88; background: transparent; border: none;")
        lay.addWidget(self._pulse)

        self._sig_start.connect(self._on_start)
        self._sig_line.connect(self._on_line)
        self._sig_end.connect(self._on_end)
        self.hide()

    def _on_start(self, tool: str, detail: str):
        self._tool_lbl.setText(tool.replace("_", " ").upper())
        self._detail_lbl.setText(detail[:120] if detail else "")
        self._log_lbl.setText("")
        self._pulse.setText("● RUNNING")
        self._pulse.setStyleSheet("color: #44ff88; background: transparent; border: none;")
        self.show()
        self._visible = True

    def _on_line(self, msg: str):
        cur = self._log_lbl.text()
        lines = (cur + "\n" + msg).strip().splitlines()
        self._log_lbl.setText("\n".join(lines[-6:]))

    def _on_end(self):
        self._pulse.setText("✓ DONE")
        self._pulse.setStyleSheet("color: #00d4ff; background: transparent; border: none;")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(4000, self._fade_hide)

    def _fade_hide(self):
        self.hide()
        self._visible = False
        self._tool_lbl.setText("Idle")
        self._detail_lbl.setText("")
        self._log_lbl.setText("")


def bind_panel(panel: ActivitySidePanel) -> None:
    global _PANEL
    _PANEL = panel


def activity_start(tool: str, detail: str = "") -> None:
    if _PANEL:
        _PANEL._sig_start.emit(tool, detail)


def activity_update(msg: str) -> None:
    if _PANEL and msg:
        _PANEL._sig_line.emit(msg.strip())


def activity_end() -> None:
    if _PANEL:
        _PANEL._sig_end.emit()
