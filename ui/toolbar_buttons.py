"""Toolbar action buttons — Stop, Screen, Add Task, Mic."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 14px;
    font-family: 'Courier New';
    font-size: 11px;
    font-weight: bold;
    min-width: 70px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {press}; }}
"""


def _btn(label: str, bg: str, fg: str, border: str, hover: str, press: str) -> QPushButton:
    b = QPushButton(label)
    b.setStyleSheet(BTN_STYLE.format(bg=bg, fg=fg, border=border, hover=hover, press=press))
    return b


def build_action_bar(on_stop, on_mini_screen, on_add_task, on_mute_toggle) -> QWidget:
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(4, 4, 4, 4)
    row.setSpacing(6)

    stop_btn = _btn("⏹ STOP", "#1a0000", "#ff4444", "#ff2222", "#2a0000", "#3a0000")
    stop_btn.setToolTip("Cancel current processing (or say 'Jarvis stop')")
    stop_btn.clicked.connect(on_stop)
    row.addWidget(stop_btn)

    screen_btn = _btn("🖥 SCREEN", "#001a1a", "#00d4ff", "#00aacc", "#002a2a", "#003a3a")
    screen_btn.setToolTip("Toggle mini screen preview overlay")
    screen_btn.clicked.connect(on_mini_screen)
    row.addWidget(screen_btn)

    task_btn = _btn("+ TASK", "#001a00", "#00ff88", "#00aa44", "#002a00", "#003a00")
    task_btn.setToolTip("Manually add a task")
    task_btn.clicked.connect(on_add_task)
    row.addWidget(task_btn)

    mute_btn = _btn("🎤 MIC", "#1a1000", "#ffaa00", "#cc8800", "#2a1800", "#3a2000")
    mute_btn.setCheckable(True)
    mute_btn.setToolTip("Toggle microphone (F4)")

    def _on_mute(checked: bool):
        mute_btn.setText("🔇 MUTED" if checked else "🎤 MIC")
        mute_btn.setStyleSheet(BTN_STYLE.format(
            bg="#2a0000" if checked else "#1a1000",
            fg="#ff4444" if checked else "#ffaa00",
            border="#cc2200" if checked else "#cc8800",
            hover="#3a0000" if checked else "#2a1800",
            press="#4a0000" if checked else "#3a2000",
        ))
        on_mute_toggle(checked)

    mute_btn.toggled.connect(_on_mute)
    row.addWidget(mute_btn)
    row.addStretch()
    return container


class AddTaskDialog(QDialog):
    task_added = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Task")
        self.setFixedWidth(400)
        self.setStyleSheet("""
            QDialog { background: #00060a; }
            QLabel  { color: #00d4ff; font-family: 'Courier New'; font-size: 11px; }
            QLineEdit, QComboBox {
                background: #010d14; color: #c0e8f0;
                border: 1px solid #0d3347; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }
            QPushButton {
                background: #001a1a; color: #00d4ff; border: 1px solid #00aacc;
                border-radius: 4px; padding: 6px 18px; font-size: 11px;
            }
            QPushButton:hover { background: #002a2a; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Task title *"))
        self._title = QLineEdit()
        self._title.setPlaceholderText("e.g. Fix ProductHandler null ref")
        lay.addWidget(self._title)

        lay.addWidget(QLabel("Description (optional)"))
        self._desc = QLineEdit()
        lay.addWidget(self._desc)

        lay.addWidget(QLabel("Category"))
        self._cat = QComboBox()
        self._cat.addItems(["personal", "work", "optimizely", "reminder", "trading", "other"])
        lay.addWidget(self._cat)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Task")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)
        self._title.returnPressed.connect(self._save)

    def _save(self):
        title = self._title.text().strip()
        if not title:
            self._title.setPlaceholderText("Title required!")
            return
        self.task_added.emit(title, self._desc.text().strip(), self._cat.currentText())
        self.accept()
