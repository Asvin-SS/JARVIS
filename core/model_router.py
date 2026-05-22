"""Select Ollama model by task type (coding, vision, reasoning, etc.)."""
from __future__ import annotations

from core.config import MODEL_ROLES


def route_model(user_text: str, default_model: str) -> str:
    """
    Pick best local model name for the utterance.
    Falls back to default_model if role model not configured in settings override.
    """
    t = (user_text or "").lower()
    settings_override = _settings_role_models()

    if any(k in t for k in ("screen", "screenshot", "what's on", "look at my", "vision", "image")):
        return settings_override.get("vision") or MODEL_ROLES["vision"]

    if any(k in t for k in ("code", "debug", "refactor", "compile", "syntax", "class ", "function ", ".cs", ".tsx", "react", "dotnet", "elastic")):
        return settings_override.get("coding") or MODEL_ROLES["coding"]

    if any(k in t for k in ("plan", "architecture", "design", "why ", "explain step", "optimizely", "configured commerce")):
        return settings_override.get("reasoning") or MODEL_ROLES["reasoning"]

    if any(k in t for k in ("summarize", "summary", "recap", "catch me up")):
        return settings_override.get("summary") or MODEL_ROLES["summary"]

    return default_model


def _settings_role_models() -> dict[str, str]:
    try:
        from llm_client import get_settings
        return get_settings().get("model_roles", {}) or {}
    except Exception:
        return {}
