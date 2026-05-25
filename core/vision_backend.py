"""
Model-agnostic vision — prefers active Ollama vision model (llava), optional Gemini key.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import requests

from core.config import OLLAMA_HOST, OLLAMA_TIMEOUT_SEC
from core.logging_setup import setup_logging

_log = setup_logging("vision")


def _has_gemini_key() -> bool:
    try:
        p = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return bool(data.get("gemini_api_key", "").strip())
    except Exception:
        pass
    return False


def _pick_vision_model() -> str:
    try:
        from llm_client import get_settings, _ollama_installed_model_names
        s = get_settings()
        preferred = s.get("vision_model") or "llava:latest"
        installed = {m["name"] for m in _ollama_installed_model_names()}
        if preferred in installed:
            return preferred
        for name in installed:
            if "llava" in name.lower() or "vision" in name.lower() or "moondream" in name.lower():
                return name
    except Exception:
        pass
    return "llava:latest"


def analyze_image_ollama(image_bytes: bytes, question: str, mime: str = "image/jpeg") -> str:
    model = _pick_vision_model()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = f"{OLLAMA_HOST.rstrip('/')}/api/chat"
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": question,
                "images": [b64],
            }
        ],
        "stream": False,
    }
    _log.info("Vision Ollama model=%s bytes=%s", model, len(image_bytes))
    r = requests.post(url, json=body, timeout=min(OLLAMA_TIMEOUT_SEC, 300))
    r.raise_for_status()
    data = r.json()
    return (data.get("message") or {}).get("content", "").strip() or "No analysis returned."


def analyze_image_gemini(image_bytes: bytes, question: str, mime: str = "image/jpeg") -> str:
    from google import genai
    from google.genai import types

    cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    key = json.loads(cfg_path.read_text(encoding="utf-8")).get("gemini_api_key", "")
    if not key:
        raise RuntimeError("No gemini_api_key configured")
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            question,
        ],
    )
    return (response.text or "").strip()


def analyze_image(image_bytes: bytes, question: str, mime: str = "image/jpeg") -> str:
    """
    Auto: try Ollama vision first, then Gemini if key exists.
    """
    try:
        return analyze_image_ollama(image_bytes, question, mime)
    except Exception as e:
        _log.warning("Ollama vision failed: %s", e)
        if _has_gemini_key():
            try:
                return analyze_image_gemini(image_bytes, question, mime)
            except Exception as e2:
                _log.error("Gemini vision failed: %s", e2)
        raise RuntimeError(
            f"Vision failed. Install a vision model: ollama pull llava:latest — {e}"
        )
