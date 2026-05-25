"""Language / Tanglish configuration for prompts and STT."""
from __future__ import annotations


def get_language_mode() -> str:
    try:
        from llm_client import get_settings
        return (get_settings().get("language_mode") or "tanglish").lower()
    except Exception:
        return "tanglish"


def get_stt_language() -> str | None:
    """Whisper language code: en, ta, or None for auto-detect."""
    try:
        from llm_client import get_settings
        code = (get_settings().get("stt_language") or "auto").lower()
        if code in ("auto", ""):
            return None
        return code
    except Exception:
        return None


def prompt_instruction() -> str:
    mode = get_language_mode()
    if mode == "tamil":
        return (
            "LANGUAGE: Reply primarily in Tamil (தமிழ்). Use clear, natural Tamil. "
            "Technical terms may stay in English when standard in industry."
        )
    if mode == "english":
        return "LANGUAGE: Reply in English unless SS uses Tamil."
    # tanglish default
    return (
        "LANGUAGE: Reply in Tanglish — natural Tamil + English mix as SS uses in Chennai/India tech. "
        "Example tone: 'SS, weather ready — Chennai la 32°C, humid ah irukku.' "
        "Be concise. Code and APIs stay in English."
    )
