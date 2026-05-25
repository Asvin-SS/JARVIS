"""Select Ollama model by task type (coding, vision, reasoning, etc.)."""
from __future__ import annotations

from core.config import MODEL_ROLES

ROUTING_RULES: list[tuple[list[str], str]] = [
    (["optimizely", "occ", "insite", "handler", ".net", "c#", "iis", "elastic"], "reasoning"),
    (["debug", "fix", "error", "exception", "traceback", "stack trace"], "coding"),
    (["code", "write", "function", "class", "implement", "refactor"], "coding"),
    (["trade", "stock", "nse", "bse", "market", "portfolio", "groww"], "general"),
    (["screen", "screenshot", "image", "look at", "vision", "camera"], "vision"),
    (["reason", "think", "explain", "why", "analyze", "plan"], "reasoning"),
]


def route_model(user_text: str, default_model: str) -> str:
    """Pick best local model name for the utterance."""
    t = (user_text or "").lower()
    settings_override = _settings_role_models()

    for keywords, role in ROUTING_RULES:
        if any(k in t for k in keywords):
            if role == "general":
                return default_model
            return settings_override.get(role) or MODEL_ROLES.get(role, default_model)

    if any(k in t for k in ("summarize", "summary", "recap", "catch me up")):
        return settings_override.get("summary") or MODEL_ROLES["summary"]

    return default_model


def _settings_role_models() -> dict[str, str]:
    try:
        from llm_client import get_settings
        return get_settings().get("model_roles", {}) or {}
    except Exception:
        return {}
