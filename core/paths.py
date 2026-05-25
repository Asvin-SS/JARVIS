"""Resolve project root reliably (avoids wrong parent.parent paths)."""
from __future__ import annotations

import sys
from pathlib import Path


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "config").is_dir() and (p / "main.py").is_file():
            return p
        if (p / "config").is_dir() and (p / "jarvis_ui.py").is_file():
            return p
        parent = p.parent
        if parent == p:
            break
        p = parent
    return Path(__file__).resolve().parent.parent


CONFIG_DIR = get_project_root() / "config"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"
