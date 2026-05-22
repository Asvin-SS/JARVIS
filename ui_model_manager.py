# ui_model_manager.py
from __future__ import annotations

import threading
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QProgressBar,
    QTabWidget, QWidget, QMessageBox, QComboBox,
)

from llm_client import (
    get_ollama_model_catalog, pull_model, remove_model,
    set_active_model, get_active_model, is_ollama_running,
    RECOMMENDED_MODELS,
)


def _btn(text: str, color: str = "#00d4ff", bg: str = "transparent") -> QPushButton:
    b = QPushButton(text)
    b.setFont(QFont("Courier New", 9))
    b.setFixedHeight(28)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: {color};
            border: 1px solid {color}; border-radius: 3px; padding: 0 8px;
        }}
        QPushButton:hover {{ background: rgba(0,212,255,0.08); }}
        QPushButton:disabled {{ color: #2a5a6a; border-color: #0d3347; }}
    """)
    return b


class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S — Model Manager")
        self.setMinimumSize(620, 480)
        self.setStyleSheet("background: #00060a; color: #8ffcff;")

        self._stop_event = threading.Event()
        self._pull_thread: threading.Thread | None = None

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── header ──────────────────────────────────────────────────
        hdr = QLabel("◈  MODEL MANAGER")
        hdr.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #00d4ff;")
        root.addWidget(hdr)

        # ollama status
        self._status_lbl = QLabel()
        self._status_lbl.setFont(QFont("Courier New", 8))
        root.addWidget(self._status_lbl)
        self._refresh_status()

        # ── tabs ─────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #0d3347; }
            QTabBar::tab { background: #010d14; color: #3a8a9a;
                           padding: 5px 14px; font-family: Courier New; font-size: 9pt; }
            QTabBar::tab:selected { color: #00d4ff; border-bottom: 2px solid #00d4ff; }
        """)
        tabs.addTab(self._build_installed_tab(), "Installed")
        tabs.addTab(self._build_catalog_tab(),   "Catalog")
        tabs.addTab(self._build_pull_tab(),       "Pull / Download")
        root.addWidget(tabs, stretch=1)

        # ── active model row ─────────────────────────────────────────
        active_row = QHBoxLayout()
        self._active_combo = QComboBox()
        self._active_combo.setFont(QFont("Courier New", 9))
        self._active_combo.setStyleSheet("""
            QComboBox { background: #010d14; color: #8ffcff;
                        border: 1px solid #0d3347; border-radius: 3px; padding: 3px 8px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #010d14; color: #8ffcff; }
        """)
        set_btn = _btn("▸  SET ACTIVE", "#00ff88")
        set_btn.clicked.connect(self._set_active)
        active_row.addWidget(QLabel("Active model:"))
        active_row.addWidget(self._active_combo, stretch=1)
        active_row.addWidget(set_btn)
        root.addLayout(active_row)

        self._refresh_installed()

    # ── status ───────────────────────────────────────────────────────
    def _refresh_status(self):
        if is_ollama_running():
            self._status_lbl.setText("● Ollama running   localhost:11434")
            self._status_lbl.setStyleSheet("color: #00ff88;")
        else:
            self._status_lbl.setText("⊘ Ollama not detected — run: ollama serve")
            self._status_lbl.setStyleSheet("color: #ff3355;")

    # ── installed tab ────────────────────────────────────────────────
    def _build_installed_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: #010d14;")
        lay = QVBoxLayout(w); lay.setSpacing(6)

        self._inst_list = QListWidget()
        self._inst_list.setStyleSheet("""
            QListWidget { background: #00060a; color: #8ffcff;
                          border: 1px solid #0d3347; font-family: Courier New; font-size: 9pt; }
            QListWidget::item:selected { background: #001f2e; color: #00d4ff; }
        """)
        lay.addWidget(self._inst_list, stretch=1)

        row = QHBoxLayout()
        refresh_btn = _btn("↺  Refresh")
        refresh_btn.clicked.connect(self._refresh_installed)
        remove_btn  = _btn("✕  Remove", "#ff3355")
        remove_btn.clicked.connect(self._remove_selected)
        row.addWidget(refresh_btn); row.addStretch(); row.addWidget(remove_btn)
        lay.addLayout(row)
        return w

    def _refresh_installed(self):
        self._inst_list.clear()
        self._active_combo.clear()
        catalog = get_ollama_model_catalog()
        current = get_active_model()
        current_name = current.get("model", "")
        for m in catalog["installed"]:
            label = f"  {m['name']}   {m['size']}   {m['modified_at']}"
            item  = QListWidgetItem(label)
            if m["name"] == current_name:
                item.setForeground(QColor("#00ff88"))
                item.setText("● " + label.strip())
            self._inst_list.addItem(item)
            self._active_combo.addItem(m["name"])
        idx = self._active_combo.findText(current_name)
        if idx >= 0:
            self._active_combo.setCurrentIndex(idx)

    def _remove_selected(self):
        item = self._inst_list.currentItem()
        if not item:
            return
        name = item.text().lstrip("● ").split()[0]
        reply = QMessageBox.question(self, "Remove model", f"Remove '{name}' from Ollama?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                remove_model(name)
                self._refresh_installed()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    # ── catalog tab ──────────────────────────────────────────────────
    def _build_catalog_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: #010d14;")
        lay = QVBoxLayout(w)

        self._cat_list = QListWidget()
        self._cat_list.setStyleSheet(self._inst_list.styleSheet())
        lay.addWidget(self._cat_list, stretch=1)

        pull_sel = _btn("⬇  Pull Selected", "#ffcc00")
        pull_sel.clicked.connect(self._pull_from_catalog)
        lay.addWidget(pull_sel)

        catalog = get_ollama_model_catalog()
        installed_names = {m["name"] for m in catalog["installed"]}
        for entry in catalog["recommended"]:
            status = "✔" if entry["name"] in installed_names else "○"
            label  = f"{status}  {entry['label']}  [{entry['tag']}]  {entry['size_est']}  —  {entry['desc']}"
            item   = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry["name"])
            if entry["name"] in installed_names:
                item.setForeground(QColor("#00ff88"))
            self._cat_list.addItem(item)
        return w

    def _pull_from_catalog(self):
        item = self._cat_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._start_pull(name)

    # ── pull tab ─────────────────────────────────────────────────────
    def _build_pull_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: #010d14;")
        lay = QVBoxLayout(w); lay.setSpacing(8)

        lay.addWidget(QLabel("Model name (e.g.  llama3.2  or  mistral:7b):"))
        self._pull_input = QLineEdit()
        self._pull_input.setFont(QFont("Courier New", 10))
        self._pull_input.setFixedHeight(30)
        self._pull_input.setStyleSheet("""
            QLineEdit { background: #000d14; color: #d8f8ff;
                        border: 1px solid #0d3347; border-radius: 3px; padding: 3px 8px; }
            QLineEdit:focus { border: 1px solid #00d4ff; }
        """)
        lay.addWidget(self._pull_input)

        self._pull_bar = QProgressBar()
        self._pull_bar.setTextVisible(True)
        self._pull_bar.setRange(0, 0)   # indeterminate until progress arrives
        self._pull_bar.setStyleSheet("""
            QProgressBar { background: #010d14; border: 1px solid #0d3347;
                           border-radius: 3px; height: 14px; text-align: center; color: #8ffcff; }
            QProgressBar::chunk { background: #00d4ff; }
        """)
        self._pull_bar.hide()
        lay.addWidget(self._pull_bar)

        self._pull_log = QListWidget()
        self._pull_log.setStyleSheet(self._inst_list.styleSheet() if hasattr(self, "_inst_list")
                                     else "background:#00060a;color:#8ffcff;font-family:Courier New;")
        lay.addWidget(self._pull_log, stretch=1)

        row = QHBoxLayout()
        self._pull_btn  = _btn("⬇  Pull Model", "#00d4ff")
        self._pull_btn.clicked.connect(self._on_pull_clicked)
        self._cancel_btn = _btn("✕  Cancel", "#ff3355")
        self._cancel_btn.clicked.connect(self._cancel_pull)
        self._cancel_btn.hide()
        row.addWidget(self._pull_btn); row.addWidget(self._cancel_btn); row.addStretch()
        lay.addLayout(row)
        return w

    def _start_pull(self, name: str):
        self._pull_input.setText(name)
        if hasattr(self, "_pull_bar"):
            self._pull_bar.show()
        if hasattr(self, "_cancel_btn"):
            self._cancel_btn.show()
        if hasattr(self, "_pull_btn"):
            self._pull_btn.setEnabled(False)
        self._stop_event.clear()

        def _run():
            def _cb(line: str):
                if line == "__complete__":
                    QTimer.singleShot(0, self._on_pull_done)
                else:
                    QTimer.singleShot(0, lambda l=line: self._pull_log.addItem(l))
            try:
                pull_model(name, progress_callback=_cb, stop_event=self._stop_event)
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Pull failed", str(e)))
                QTimer.singleShot(0, self._on_pull_done)

        self._pull_thread = threading.Thread(target=_run, daemon=True)
        self._pull_thread.start()

    def _on_pull_clicked(self):
        name = self._pull_input.text().strip()
        if not name:
            return
        self._pull_log.clear()
        self._start_pull(name)

    def _cancel_pull(self):
        self._stop_event.set()

    def _on_pull_done(self):
        if hasattr(self, "_pull_bar"):
            self._pull_bar.hide()
        if hasattr(self, "_cancel_btn"):
            self._cancel_btn.hide()
        if hasattr(self, "_pull_btn"):
            self._pull_btn.setEnabled(True)
        self._refresh_installed()
        self._refresh_status()

    # ── set active ───────────────────────────────────────────────────
    def _set_active(self):
        name = self._active_combo.currentText().strip()
        if not name:
            return
        try:
            set_active_model("ollama", name)
            self._refresh_installed()
            QMessageBox.information(self, "Done", f"Active model set to:  {name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))