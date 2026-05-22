# config/__init__.py
import json
import platform
from pathlib import Path

_BASE   = Path(__file__).resolve().parent.parent
_SETTINGS = _BASE / "config" / "settings.json"
_API_KEYS = _BASE / "config" / "api_keys.json"

def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def get_settings() -> dict:
    return _load(_SETTINGS)

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux' — reads from settings, falls back to auto-detect."""
    saved = get_settings().get("os_system", "")
    if saved:
        return saved.lower()
    s = platform.system().lower()
    return {"darwin": "mac", "windows": "windows"}.get(s, "linux")

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"

def get_active_provider() -> str:
    return get_settings().get("active_provider", "ollama")

def get_active_model() -> str:
    return get_settings().get("active_model", "llama3.2")