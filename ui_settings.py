"""Mark-XXXIX — tabbed Settings dialog (models, voice, smart home, startup, about)."""
from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton, QButtonGroup,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from llm_client import (
    RECOMMENDED_MODELS,
    get_active_model,
    get_api_config,
    get_model_catalog,
    get_ollama_models,
    get_settings,
    pull_model,
    remove_model,
    save_settings,
    set_active_model,
    warm_up_model,
    is_ollama_running,
)

_STYLE = "background: #00060a; color: #8ffcff;"
_CARD = "background: #000d14; border: 1px solid #0d3347; border-radius: 4px;"


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Mark-XXXIX")
        self.resize(620, 720)
        self.setStyleSheet(_STYLE)
        self._pull_stop = threading.Event()
        self._setup_ui()
        self._load_all()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._tab_models(), "Models")
        tabs.addTab(self._tab_voice(), "Voice")
        tabs.addTab(self._tab_smart_home(), "Smart Home")
        tabs.addTab(self._tab_startup(), "Startup")
        tabs.addTab(self._tab_about(), "About")
        root.addWidget(tabs)

        foot = QHBoxLayout()
        save = QPushButton("SAVE & APPLY")
        save.setStyleSheet("background: #00d4ff; color: #00060a; font-weight: bold; padding: 8px;")
        save.clicked.connect(self._save_all)
        foot.addWidget(save)
        close = QPushButton("CLOSE")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        root.addLayout(foot)

    def _tab_models(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel("ACTIVE MODEL (Ollama)"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._model_box = QWidget()
        self._model_lay = QVBoxLayout(self._model_box)
        scroll.setWidget(self._model_box)
        lay.addWidget(scroll, stretch=1)

        self._model_group = QButtonGroup(self)
        self._model_group.buttonClicked.connect(self._on_model_pick)

        warm = QPushButton("Warm up selected model")
        warm.clicked.connect(self._warm_up)
        lay.addWidget(warm)

        lay.addWidget(QLabel("INSTALL OPEN-SOURCE MODELS"))
        cat_scroll = QScrollArea()
        cat_scroll.setWidgetResizable(True)
        self._cat_box = QWidget()
        self._cat_lay = QVBoxLayout(self._cat_box)
        cat_scroll.setWidget(self._cat_box)
        lay.addWidget(cat_scroll, stretch=2)

        lay.addWidget(QLabel("API KEYS (Anthropic / OpenAI only)"))
        form = QFormLayout()
        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._anthropic_key = QLineEdit()
        self._anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("OpenAI:", self._openai_key)
        form.addRow("Anthropic:", self._anthropic_key)
        lay.addLayout(form)
        key_row = QHBoxLayout()
        for label, prov in [("Test OpenAI", "openai"), ("Test Anthropic", "anthropic")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, p=prov: self._test_key(p))
            key_row.addWidget(b)
        lay.addLayout(key_row)
        return w

    def _tab_voice(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        self._speech_on = QCheckBox("Enable speech (TTS on every reply)")
        self._speech_on.setChecked(True)
        self._require_prefix = QCheckBox('Require "Jarvis" prefix on voice commands')
        self._require_prefix.setChecked(True)
        lay.addRow(self._speech_on)
        lay.addRow(self._require_prefix)
        self._wake_sens = QComboBox()
        self._wake_sens.addItems(["Low", "Medium", "High"])
        lay.addRow("Wake word sensitivity:", self._wake_sens)
        lay.addRow("", QLabel("Mic mute (F4) only stops listening — not TTS or dashboard."))
        return w

    def _tab_smart_home(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self._ha_url = QLineEdit()
        self._ha_url.setPlaceholderText("http://homeassistant.local:8123")
        self._ha_token = QLineEdit()
        self._ha_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Home Assistant URL:", self._ha_url)
        form.addRow("Access token:", self._ha_token)
        lay.addLayout(form)
        row = QHBoxLayout()
        test = QPushButton("Test connection")
        test.clicked.connect(self._test_ha)
        save_ha = QPushButton("Save")
        save_ha.clicked.connect(self._save_ha_only)
        row.addWidget(test)
        row.addWidget(save_ha)
        lay.addLayout(row)
        self._ha_status = QLabel("Status: not configured")
        self._ha_status.setWordWrap(True)
        lay.addWidget(self._ha_status)
        lay.addStretch()
        return w

    def _tab_startup(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._chk_tray = QCheckBox("Start minimised to tray (after first launch)")
        self._chk_greeting = QCheckBox("Run greeting sequence on startup")
        self._chk_tasks = QCheckBox("Show active tasks on startup")
        self._weather_city = QLineEdit()
        self._weather_city.setPlaceholderText("City for weather (e.g. Chennai)")
        lay.addWidget(self._chk_tray)
        lay.addWidget(self._chk_greeting)
        lay.addWidget(self._chk_tasks)
        lay.addWidget(QLabel("Default weather city:"))
        lay.addWidget(self._weather_city)
        lay.addStretch()
        return w

    def _tab_about(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        txt = QLabel(
            "Mark-XXXIX\n"
            "Personal AI Agent — A product of SS\n"
            "Version: 1.0.0\n\n"
            "Private, local, always-on assistant for coding, file editing,\n"
            "screen analysis, tasks, smart home, and market monitoring.\n\n"
            "Primary model: mistral:latest (Ollama)\n"
            "Optional: Anthropic Claude / OpenAI GPT (API keys)"
        )
        txt.setWordWrap(True)
        txt.setFont(QFont("Courier New", 9))
        lay.addWidget(txt)
        lay.addStretch()
        return w

    def _load_all(self):
        settings = get_settings()
        keys = get_api_config()
        self._openai_key.setText(keys.get("openai_api_key", ""))
        self._anthropic_key.setText(keys.get("anthropic_api_key", ""))
        sens = settings.get("wake_sensitivity", "medium").lower()
        idx = {"low": 0, "medium": 1, "high": 2}.get(sens, 1)
        self._wake_sens.setCurrentIndex(idx)
        ha = settings.get("home_assistant", {}) or {}
        self._ha_url.setText(ha.get("url", ""))
        self._ha_token.setText(ha.get("token", ""))
        self._speech_on.setChecked(settings.get("speech_enabled", True))
        self._require_prefix.setChecked(settings.get("require_jarvis_prefix", True))
        self._chk_tray.setChecked(settings.get("start_minimized", True))
        self._chk_greeting.setChecked(settings.get("run_greeting", True))
        self._chk_tasks.setChecked(settings.get("show_tasks_startup", True))
        self._weather_city.setText(settings.get("weather_city", ""))
        self._reload_models()
        self._reload_catalog()

    def _reload_models(self):
        while self._model_lay.count():
            item = self._model_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._model_group = QButtonGroup(self)
        self._model_group.buttonClicked.connect(self._on_model_pick)
        active = get_active_model()
        for name in get_ollama_models():
            info = next((m for m in RECOMMENDED_MODELS if m["name"] in name or name.startswith(m["name"])), None)
            desc = info["desc"] if info else "Installed local model"
            tag = info.get("tag", "balanced") if info else "installed"
            rb = QRadioButton(name)
            if name == active.get("model"):
                rb.setChecked(True)
            self._model_group.addButton(rb)
            card = QFrame()
            card.setStyleSheet(_CARD)
            cl = QHBoxLayout(card)
            cl.addWidget(rb)
            col = QVBoxLayout()
            col.addWidget(QLabel(desc))
            col.addWidget(QLabel(tag.upper()))
            cl.addLayout(col, stretch=1)
            self._model_lay.addWidget(card)
        self._model_lay.addStretch()

    def _reload_catalog(self):
        while self._cat_lay.count():
            item = self._cat_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cat = get_model_catalog()
        for entry in cat.get("available", []):
            card = QFrame()
            card.setStyleSheet(_CARD)
            cl = QVBoxLayout(card)
            title = QLabel(f"{entry['name']}  {entry.get('size_est', '')}  [{entry.get('tag', '')}]")
            title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            cl.addWidget(title)
            cl.addWidget(QLabel(entry.get("desc", "")))
            bar = QProgressBar()
            bar.setVisible(False)
            cl.addWidget(bar)
            row = QHBoxLayout()
            pull_name = entry["pull_name"]
            if entry.get("installed"):
                use_btn = QPushButton("Use")
                use_btn.clicked.connect(lambda _, n=pull_name: self._use_model(n))
                row.addWidget(use_btn)
                rm = QPushButton("Remove")
                rm.clicked.connect(lambda _, n=pull_name: self._remove_model(n))
                row.addWidget(rm)
            else:
                ins = QPushButton("Install")
                ins.clicked.connect(lambda _, n=pull_name, b=bar: self._install_model(n, b))
                row.addWidget(ins)
            cl.addLayout(row)
            self._cat_lay.addWidget(card)
        self._cat_lay.addStretch()

    def _on_model_pick(self, btn):
        set_active_model("ollama", btn.text())
        if self.parent() and hasattr(self.parent(), "_dash"):
            self.parent()._dash.refresh_status()

    def _use_model(self, name: str):
        set_active_model("ollama", name)
        self._reload_models()
        QMessageBox.information(self, "Model", f"Active model set to {name}")

    def _warm_up(self):
        if not is_ollama_running():
            QMessageBox.warning(self, "Ollama", "Ollama is not running. Start with: ollama serve")
            return
        threading.Thread(target=warm_up_model, daemon=True).start()

    def _install_model(self, name: str, bar: QProgressBar):
        if not is_ollama_running():
            QMessageBox.warning(self, "Ollama", "Ollama is not running.")
            return
        bar.setVisible(True)
        bar.setValue(0)
        self._pull_stop.clear()

        def _progress(a, b=""):
            if isinstance(a, int):
                QTimer.singleShot(0, lambda: bar.setValue(a))
            elif a == "__complete__":
                QTimer.singleShot(0, lambda: (bar.setVisible(False), self._reload_models(), self._reload_catalog()))

        def _task():
            try:
                pull_model(name, progress_callback=_progress, stop_event=self._pull_stop)
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Install failed", str(e)))

        threading.Thread(target=_task, daemon=True).start()

    def _remove_model(self, name: str):
        if QMessageBox.question(self, "Remove", f"Remove {name}?") != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_model(name)
            self._reload_models()
            self._reload_catalog()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _test_key(self, provider: str):
        key = self._openai_key.text() if provider == "openai" else self._anthropic_key.text()
        if not key.strip():
            QMessageBox.warning(self, "Test", "Enter a key first.")
            return
        QMessageBox.information(self, "Test", f"{provider.upper()} key saved format looks OK. Full API test on next chat.")

    def _test_ha(self):
        try:
            from smart_home import SmartHomeManager
            mgr = SmartHomeManager()
            mgr.configure_home_assistant(self._ha_url.text(), self._ha_token.text())
            devs = mgr.list_devices()
            self._ha_status.setText(f"✓ Connected — {len(devs)} device(s) configured locally.")
        except Exception as e:
            self._ha_status.setText(f"✕ {e}")

    def _save_ha_only(self):
        settings = get_settings()
        settings["home_assistant"] = {
            "url": self._ha_url.text().strip(),
            "token": self._ha_token.text().strip(),
        }
        save_settings(settings)
        QMessageBox.information(self, "Saved", "Home Assistant settings saved.")

    def _save_all(self):
        settings = get_settings()
        settings["openai_api_key"] = self._openai_key.text().strip()
        settings["anthropic_api_key"] = self._anthropic_key.text().strip()
        sens = ["low", "medium", "high"][self._wake_sens.currentIndex()]
        settings["wake_sensitivity"] = sens
        settings["speech_enabled"] = self._speech_on.isChecked()
        settings["require_jarvis_prefix"] = self._require_prefix.isChecked()
        settings["home_assistant"] = {
            "url": self._ha_url.text().strip(),
            "token": self._ha_token.text().strip(),
        }
        settings["start_minimized"] = self._chk_tray.isChecked()
        settings["run_greeting"] = self._chk_greeting.isChecked()
        settings["show_tasks_startup"] = self._chk_tasks.isChecked()
        settings["weather_city"] = self._weather_city.text().strip()
        save_settings(settings)
        try:
            from llm_client import _save_json, API_KEYS_PATH, CONFIG_DIR
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _save_json(API_KEYS_PATH, {
                "openai_api_key": settings.get("openai_api_key", ""),
                "anthropic_api_key": settings.get("anthropic_api_key", ""),
            })
        except Exception:
            pass
        self.accept()


# Backward compatibility
ModelManagerDialog = SettingsDialog
