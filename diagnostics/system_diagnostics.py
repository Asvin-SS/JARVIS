"""System Diagnostics — validates core subsystems (Phase 12)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _check(name: str, fn) -> dict[str, Any]:
    try:
        fn()
        return {"ok": True, "detail": "pass"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def run_diagnostics() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}

    def ollama():
        from llm_client import is_ollama_running, get_active_model
        assert is_ollama_running(), "Ollama not reachable"
        m = get_active_model()
        assert m.get("model"), "no active model"

    def sqlite_db():
        from db.database import DB_PATH, get_db
        assert DB_PATH.exists(), "jarvis.db missing"
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()

    def tts():
        import pyttsx3
        pyttsx3.init()

    def whisper():
        from faster_whisper import WhisperModel  # noqa: F401

    def weather():
        from services.weather_service import fetch_weather
        w = fetch_weather("Chennai")
        assert w.get("raw_line")

    report["ollama"] = _check("ollama", ollama)
    report["sqlite"] = _check("sqlite", sqlite_db)
    report["tts"] = _check("tts", tts)
    report["whisper"] = _check("whisper", whisper)
    report["weather"] = _check("weather", weather)
    report["config_dir"] = {
        "ok": Path(__file__).resolve().parent.parent.joinpath("config").exists(),
        "detail": "config/",
    }
    return report


def format_report(report: dict[str, dict[str, Any]]) -> str:
    lines = ["Mark-XXXIX Diagnostics", "=" * 32]
    for k, v in report.items():
        status = "PASS" if v.get("ok") else "FAIL"
        lines.append(f"  {k}: {status} — {v.get('detail', '')}")
    return "\n".join(lines)
