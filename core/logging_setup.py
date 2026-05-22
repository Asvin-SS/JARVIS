"""Centralized logging for Mark-XXXIX."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.config import LOGS_DIR, ensure_runtime_dirs

_CONFIGURED = False


def setup_logging(name: str = "jarvis", level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    ensure_runtime_dirs()
    logger = logging.getLogger(name)
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(LOGS_DIR / "jarvis.log", encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(level)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)

    root = logging.getLogger("jarvis")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(fh)
        root.addHandler(ch)

    _CONFIGURED = True
    return logging.getLogger(name)
