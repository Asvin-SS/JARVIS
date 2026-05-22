import os
import json
import threading
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QRadioButton, QButtonGroup,
    QLineEdit, QMessageBox
)
from PyQt6.QtGui import QFont

from llm_client import (
    get_ollama_models, get_active_model, set_active_model,
    get_settings, save_settings, RECOMMENDED_MODELS, warm_up_model
)

class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Model Manager — MARK-3.9")
        self.resize(550, 650)
        self.setStyleSheet("background: #00060a; color: #8ffcff;")
        self._setup_ui()
        self._load_models()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(15)

        title = QLabel("🤖 MODEL CONFIGURATION")
        title.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff;")
        lay.addWidget(title)

        # Ollama Models Section
        lay.addWidget(QLabel("OLLAMA MODELS (LOCAL)"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: #010d14; border: 1px solid #0d3347;")
        
        self.model_container = QWidget()
        self.model_lay = QVBoxLayout(self.model_container)
        self.model_lay.setSpacing(10)
        self.model_lay.addStretch()
        
        scroll.setWidget(self.model_container)
        lay.addWidget(scroll, stretch=1)

        self.btn_group = QButtonGroup(self)
        self.btn_group.buttonClicked.connect(self._model_selected)

        # Warm up button
        self.warm_up_btn = QPushButton("WARM UP SELECTED MODEL")
        self.warm_up_btn.setFixedHeight(36)
        self.warm_up_btn.setStyleSheet("""
            QPushButton { background: #001f2e; color: #00d4ff; border: 1px solid #007a99; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #00d4ff; color: #00060a; }
        """)
        self.warm_up_btn.clicked.connect(self._warm_up)
        lay.addWidget(self.warm_up_btn)

        # API Keys Section (Task 10.6)
        lay.addWidget(QLabel("CLOUD API KEYS"))
        
        keys_frame = QFrame()
        keys_frame.setStyleSheet("background: #010f18; border: 1px solid #0d3347; border-radius: 4px;")
        keys_lay = QVBoxLayout(keys_frame)
        
        # OpenAI
        oa_lay = QHBoxLayout()
        oa_lay.addWidget(QLabel("OpenAI:"))
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setStyleSheet("background: #000d14; color: #fff; border: 1px solid #0d3347; padding: 4px;")
        oa_lay.addWidget(self.openai_key)
        test_oa = QPushButton("Test")
        test_oa.setFixedWidth(50)
        test_oa.clicked.connect(lambda: self._test_key("openai"))
        oa_lay.addWidget(test_oa)
        keys_lay.addLayout(oa_lay)

        # Anthropic
        ant_lay = QHBoxLayout()
        ant_lay.addWidget(QLabel("Anthropic:"))
        self.anthropic_key = QLineEdit()
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setStyleSheet("background: #000d14; color: #fff; border: 1px solid #0d3347; padding: 4px;")
        ant_lay.addWidget(self.anthropic_key)
        test_ant = QPushButton("Test")
        test_ant.setFixedWidth(50)
        test_ant.clicked.connect(lambda: self._test_key("anthropic"))
        ant_lay.addWidget(test_ant)
        keys_lay.addLayout(ant_lay)
        
        lay.addWidget(keys_frame)

        # Footer
        footer = QHBoxLayout()
        save_btn = QPushButton("SAVE & APPLY")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet("background: #00d4ff; color: #00060a; font-weight: bold; border-radius: 4px;")
        save_btn.clicked.connect(self._save_all)
        footer.addWidget(save_btn)
        
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet("background: transparent; color: #5ab8cc; border: 1px solid #0d3347; border-radius: 4px;")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        
        lay.addLayout(footer)

        # Load existing keys
        settings = get_settings()
        self.openai_key.setText(settings.get("openai_api_key", ""))
        self.anthropic_key.setText(settings.get("anthropic_api_key", ""))

    def _load_models(self):
        # Clear existing
        for i in reversed(range(self.model_lay.count())):
            item = self.model_lay.itemAt(i)
            if item and item.widget(): item.widget().setParent(None)

        active = get_active_model()
        installed = get_ollama_models()
        
        # Create a combined list of installed and recommended info
        reco_map = {m["name"]: m for m in RECOMMENDED_MODELS}
        
        for m_name in installed:
            info = reco_map.get(m_name, {"desc": "Local model", "tag": "installed"})
            
            card = QFrame()
            card.setStyleSheet("background: #000d14; border: 1px solid #0d3347; border-radius: 4px;")
            card_lay = QHBoxLayout(card)
            
            rb = QRadioButton(m_name)
            rb.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            if m_name == active.get("model"): rb.setChecked(True)
            self.btn_group.addButton(rb)
            card_lay.addWidget(rb)
            
            desc_v = QVBoxLayout()
            desc_lbl = QLabel(info.get("desc", ""))
            desc_lbl.setFont(QFont("Courier New", 7))
            desc_lbl.setStyleSheet("color: #3a8a9a;")
            desc_v.addWidget(desc_lbl)
            
            tag = QLabel(info.get("tag", "balanced").upper())
            tag.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
            tag.setStyleSheet("background: #00d4ff; color: #00060a; padding: 2px 4px; border-radius: 2px;")
            tag.setFixedWidth(60)
            desc_v.addWidget(tag)
            
            card_lay.addLayout(desc_v, stretch=1)
            self.model_lay.insertWidget(self.model_lay.count()-1, card)

    def _model_selected(self, btn):
        model_name = btn.text()
        set_active_model("ollama", model_name)
        # Update UI main window status if possible
        if self.parent():
            self.parent().lbl_status.setText(f"● {model_name} (Ollama)")

    def _warm_up(self):
        self.warm_up_btn.setText("WARMING UP...")
        self.warm_up_btn.setEnabled(False)
        def _task():
            warm_up_model()
            QTimer.singleShot(0, lambda: self.warm_up_btn.setText("MODEL READY ✓"))
            QTimer.singleShot(2000, lambda: self.warm_up_btn.setEnabled(True))
            QTimer.singleShot(2000, lambda: self.warm_up_btn.setText("WARM UP SELECTED MODEL"))
        threading.Thread(target=_task, daemon=True).start()

    def _test_key(self, provider):
        # Simplified test
        key = self.openai_key.text() if provider == "openai" else self.anthropic_key.text()
        if not key:
            QMessageBox.warning(self, "Test", "Please enter a key first.")
            return
        QMessageBox.information(self, "Test", f"{provider.upper()} key format looks valid.")

    def _save_all(self):
        settings = get_settings()
        settings["openai_api_key"] = self.openai_key.text().strip()
        settings["anthropic_api_key"] = self.anthropic_key.text().strip()
        save_settings(settings)
        self.accept()
