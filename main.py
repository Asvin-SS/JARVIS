"""
MARK XXXIX — JarvisLocal
Voice pipeline: sounddevice mic → faster-whisper STT → Ollama LLM (tool calls) → pyttsx3 TTS → sounddevice playback
Chat pipeline:  text input box → same Ollama LLM path
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import threading
import traceback
import importlib
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

try:
    import speech_recognition as sr
    _SR_OK = True
except ImportError:
    _SR_OK = False
    print("[JARVIS] speech_recognition not installed — wake word disabled. pip install SpeechRecognition pyaudio")

import winsound # For beep/chime
try:
    from faster_whisper import WhisperModel as _WhisperModel
    _WHISPER_OK = True
except ImportError:
    _WHISPER_OK = False
    print("[JARVIS] faster-whisper not installed — voice input disabled. pip install faster-whisper")

try:
    import pyttsx3 as _pyttsx3
    _TTS_OK = True
except ImportError:
    _TTS_OK = False
    print("[JARVIS] pyttsx3 not installed — voice output disabled. pip install pyttsx3")

# ── project infrastructure ────────────────────────────────────────────────────
try:
    from core.config import ensure_runtime_dirs
    from core.logging_setup import setup_logging
    ensure_runtime_dirs()
    _jarvis_log = setup_logging("main")
except ImportError:
    _jarvis_log = None

# ── project imports ───────────────────────────────────────────────────────────
from jarvis_ui import JarvisUI
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
from llm_client import chat_with_tools, get_active_model, get_settings, warm_up_model, unified_chat
from db.database import (
    init_db, get_db, get_active_tasks, get_watchlist, add_session,
    save_task, log_conversation,
)

from actions.market_tracker    import run as market_tracker
from actions.file_processor    import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR    = get_base_dir()
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
IDENTITY_PATH = BASE_DIR / "core" / "identity.txt"

# ── audio constants ───────────────────────────────────────────────────────────
MIC_SAMPLE_RATE  = 16_000   # Whisper expects 16 kHz
MIC_CHANNELS     = 1
MIC_DTYPE        = "int16"
CHUNK_DURATION   = 0.5      # seconds per mic chunk fed into VAD buffer
SILENCE_TIMEOUT  = 1.8      # seconds of silence before ending utterance
ENERGY_THRESHOLD = 300      # RMS threshold — tune up if too sensitive


def _load_system_prompt() -> str:
    parts = []
    if IDENTITY_PATH.exists():
        try:
            parts.append(IDENTITY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    if PROMPT_PATH.exists():
        try:
            parts.append(PROMPT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    if parts:
        return "\n\n".join(parts)
    return (
        "You are Jarvis, a personal AI assistant for SS. "
        "Be concise and direct. Use tools when needed. Ask before external actions."
    )


def _is_yes(text: str) -> bool:
    """Strict yes — word tokens only (avoids 'ok' inside longer commands)."""
    t = text.lower().strip()
    tokens = set(re.sub(r"[^\w\s]", " ", t).split())
    if tokens & {"yes", "yeah", "yep", "sure", "ok", "okay", "please", "y"}:
        return True
    return any(p in t for p in ("do it", "go ahead", "go on"))


def _is_no(text: str) -> bool:
    t = text.lower().strip()
    tokens = set(re.sub(r"[^\w\s]", " ", t).split())
    if tokens & {"no", "nope", "skip", "later", "nah"}:
        return True
    return any(p in t for p in ("don't", "not now", "skip it"))


def _is_real_command(text: str) -> bool:
    """User asked a real question/command — exit greeting wizard."""
    t = text.lower().strip()
    if len(t) < 4:
        return False
    keywords = (
        "what", "how", "why", "when", "where", "who", "tell", "show", "list",
        "task", "tasks", "pending", "weather", "watchlist", "groww", "open",
        "pull", "debug", "code", "fix", "create", "build", "search", "news",
        "panunga", "sollu", "enna", "veppu", "vannila", "tamil",
    )
    return any(k in t for k in keywords)


def _is_skip_all(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in ("skip all", "just start", "skip everything", "start listening"))


def _is_stop_command(text: str) -> bool:
    """Only explicit stop/cancel — do not interrupt on background noise."""
    t = re.sub(r"[^\w\s']", " ", (text or "").lower()).strip()
    if not t:
        return False
    phrases = (
        "jarvis stop", "stop jarvis", "okay jarvis stop", "ok jarvis stop",
        "please stop", "stop please", "stop listening", "cancel jarvis",
        "jarvis cancel", "just stop",
    )
    if any(p in t for p in phrases):
        return True
    words = t.split()
    return words == ["stop"] or (len(words) <= 3 and words[-1] == "stop")


def _tts_sanitize(text: str, max_len: int = 600) -> str:
    """Prepare text for speech — remove markdown, keep real content."""
    if not text or not text.strip():
        return ""
    text = re.sub(r"```[\s\S]*?```", "code block omitted", text)
    text = re.sub(r"`([^`]+)`", lambda m: m.group(1).strip(), text)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and "]" in s[:60] and len(s) < 80:
            continue
        if s.upper().startswith("ASSISTANT]") or s.upper().startswith("[CURRENT"):
            continue
        if s:
            lines.append(s)
    clean = " ".join(lines).strip()
    if len(clean) > max_len:
        parts = re.split(r"(?<=[.!?])\s+", clean)
        result = ""
        for p in parts:
            if len(result) + len(p) + 1 <= max_len:
                result = (result + " " + p).strip()
            else:
                break
        clean = result or clean[:max_len]
    return clean


def _speech_enabled() -> bool:
    """Always returns True unless EXPLICITLY set to False in settings."""
    try:
        from llm_client import get_settings
        val = get_settings().get("speech_enabled", True)
        if val is None or val == "":
            return True
        return bool(val)
    except Exception:
        return True


def _try_fast_command(text: str, jarvis: "JarvisLocal") -> bool:
    """Local commands without LLM — tasks, watchlist, weather refresh."""
    import re
    t = text.strip()
    low = t.lower()
    ui = jarvis.ui

    m = re.match(r"^(?:jarvis[,]?\s*)?add\s+task[:\s]+(.+)$", t, re.I)
    if m:
        title = m.group(1).strip()
        save_task(title, "", "personal")
        ui.write_log(f"SYS: Task added — {title}")
        jarvis._speak(f"Added task: {title}")
        if hasattr(ui._win, "_refresh_side"):
            ui._win._refresh_side()
        return True

    add_pat = re.compile(
        r"add\s+(.+?)\s+(?:to|in|into)\s+(?:my\s+)?watchlist",
        re.IGNORECASE,
    )
    m = add_pat.search(t)
    if m:
        raw_sym = m.group(1).strip()
        from actions.market_tracker import run as mt_run, _normalise_symbol
        result = mt_run({"action": "add", "symbol": raw_sym}, player=ui)
        ui.write_log(f"SYS: {result}")
        jarvis._speak(f"Added {_normalise_symbol(raw_sym)} to your watchlist.")
        return True

    rem_pat = re.compile(
        r"remove\s+(.+?)\s+(?:from|off)\s+(?:my\s+)?watchlist",
        re.IGNORECASE,
    )
    m = rem_pat.search(t)
    if m:
        raw_sym = m.group(1).strip()
        from actions.market_tracker import run as mt_run, _normalise_symbol
        result = mt_run({"action": "remove", "symbol": raw_sym}, player=ui)
        ui.write_log(f"SYS: {result}")
        jarvis._speak(f"Removed {_normalise_symbol(raw_sym)} from watchlist.")
        return True

    if re.search(r"show|list|display|what.s on", low) and "watchlist" in low:
        from actions.market_tracker import run as mt_run
        result = mt_run({"action": "show_watchlist"}, player=ui)
        ui.write_log(f"Jarvis: {result}")
        jarvis._speak(result[:200])
        return True

    price_pat = re.compile(
        r"(?:price|rate|value|how much)\s+(?:of|is|for)?\s+(.+?)(?:\s+stock|\s+share|\?|$)",
        re.IGNORECASE,
    )
    m = price_pat.search(t)
    if not m:
        price_pat2 = re.compile(r"(.+?)\s+(?:stock\s+)?price", re.IGNORECASE)
        m = price_pat2.search(t)
    if m and any(kw in low for kw in ("price", "rate", "trading at", "worth")):
        raw_sym = m.group(1).strip()
        from actions.market_tracker import run as mt_run
        result = mt_run({"action": "get_price", "symbol": raw_sym}, player=ui)
        ui.write_log(f"Jarvis: {result}")
        jarvis._speak(result[:200])
        return True

    if "watchlist" in low or re.search(r"\b(groww|grow)\b", low):
        from actions.market_tracker import run as mt_run
        result = mt_run({"action": "show_watchlist"}, player=ui)
        ui.write_log(f"Jarvis: {result}")
        jarvis._speak(result[:200])
        return True

    if "refresh dashboard" in low or "refresh weather" in low:
        if hasattr(ui._win, "_refresh_side"):
            ui._win._refresh_side()
        ui.write_log("SYS: Dashboard refreshed.")
        jarvis._speak("Dashboard updated.")
        return True

    if low in ("show window", "open window", "show jarvis"):
        ui.show()
        return True

    if re.search(r"\b(tamil|tanglish)\b", low) and re.search(
        r"\b(speak|understand|language|tamil|tanglish|pesu)\b", low
    ):
        msg = (
            "Yes SS — I understand Tamil and Tanglish. "
            "You can speak Tamil; I'll reply in Tanglish unless you want pure Tamil."
        )
        ui.write_log(f"Jarvis: {msg}")
        jarvis._speak(msg)
        return True

    if re.search(r"\bopen\b.*\b(chrome|browser)\b", low) and "youtube" in low:
        try:
            browser_control({"action": "open", "url": "https://www.youtube.com"})
            ui.write_log("Jarvis: Opening YouTube in the browser.")
            jarvis._speak("Opening YouTube, SS.")
        except Exception as e:
            ui.write_log(f"Jarvis: {e}")
        return True

    if re.search(r"\bopen\b.*\bchrome\b", low):
        try:
            open_app(parameters={"app_name": "Chrome"}, response=None, player=ui)
            ui.write_log("Jarvis: Opening Chrome.")
            jarvis._speak("Opening Chrome.")
        except Exception as e:
            ui.write_log(f"Jarvis: {e}")
        return True

    if re.search(r"\b(list|show|what are|tell me|recap|pending|impending)\b.*\b(task|todo)s?\b", low) or re.search(r"\b(task|todo)s?\b.*\b(list|show|pending)\b", low):
        tasks = get_active_tasks()
        seen: set[str] = set()
        titles = []
        for t in tasks:
            title = (t.get("title") or "").strip()
            if title and title.lower() not in seen:
                seen.add(title.lower())
                titles.append(title)
        if not titles:
            msg = "You have no active tasks."
        else:
            msg = f"You have {len(titles)} active tasks: " + "; ".join(titles[:8])
        ui.write_log(f"Jarvis: {msg}")
        jarvis._speak(msg[:220])
        if hasattr(ui._win, "_refresh_side"):
            ui._win._refresh_side()
        return True

    if re.search(r"\b(weather|temperature|forecast)\b", low) or ("pull" in low and "weather" in low):
        try:
            from llm_client import get_settings
            city = get_settings().get("weather_city") or "Chennai"
            from services.weather_service import format_weather_line
            line = format_weather_line(city)
            ui.write_log(f"Jarvis: {line}")
            jarvis._speak(line[:200])
            if hasattr(ui._win, "_refresh_side"):
                ui._win._refresh_side()
        except Exception as e:
            ui.write_log(f"Jarvis: Weather unavailable — {e}")
            jarvis._speak("Weather service is unavailable right now.")
        return True

    # YouTube play — fast path (no LLM)
    m = re.search(r"play\s+(.+?)\s+(?:on|in|via)\s+youtube", low)
    if not m:
        m = re.search(r"(?:youtube|yt)\s+(?:play|open|search)\s+(.+)", low)
    if not m and "youtube" in low and any(w in low for w in ("play", "song", "music", "video")):
        for trigger in ("play ", "youtube "):
            idx = low.find(trigger)
            if idx >= 0:
                query = t[idx + len(trigger):].strip()
                if query:
                    class _M:
                        @staticmethod
                        def group(n):
                            return query
                    m = _M()
                    break

    if m:
        try:
            query = m.group(1) if hasattr(m, "group") else str(m)
            from actions.youtube_video import youtube_video
            youtube_video({"action": "play", "query": str(query)}, player=ui)
            ui.write_log(f"Jarvis: Playing '{query}' on YouTube.")
            jarvis._speak(f"Playing {query} on YouTube.")
        except Exception as e:
            ui.write_log(f"Jarvis: YouTube error — {e}")
            import webbrowser
            from urllib.parse import quote_plus
            webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(str(query))}")
        return True

    if re.search(r"open\s+(?:vs\s?code|visual\s+studio\s+code|vs)\b", low) or "open vs" in low:
        try:
            from llm_client import get_settings
            occ_path = (get_settings().get("coding") or {}).get("optimizely_path") or "."
            from actions.system_access import open_vs_code_with_folder
            result = open_vs_code_with_folder(occ_path)
            ui.write_log(f"Jarvis: {result}")
            jarvis._speak(result)
        except Exception as e:
            ui.write_log(f"Jarvis: {e}")
        return True

    # Open URL / website
    m2 = re.search(r"open\s+(https?://\S+|[\w.-]+\.\w{2,})", low)
    if m2:
        url = m2.group(1)
        try:
            import webbrowser
            webbrowser.open(url if url.startswith("http") else "https://" + url)
            ui.write_log(f"Jarvis: Opening {url}")
            jarvis._speak(f"Opening {url}")
        except Exception as e:
            ui.write_log(f"Jarvis: {e}")
        return True

    return False


def _parse_voice_command(text: str) -> str | None:
    """
    When require_jarvis_prefix is on, ignore utterances that do not address Jarvis.
    Reduces false triggers from TV / background conversation.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        from llm_client import get_settings
        if not get_settings().get("require_jarvis_prefix", False):
            return raw
    except Exception:
        return raw

    low = raw.lower()
    prefixes = (
        "jarvis,",
        "hey jarvis,",
        "hey jarvis ",
        "jarvis ",
        "jarvis do ",
        "jarvis open ",
        "jarvis create ",
        "wake up jarvis ",
    )
    for p in prefixes:
        if low.startswith(p):
            rest = raw[len(p) :].strip()
            return rest if rest else None
    if low == "jarvis" or low.startswith("jarvis:"):
        return raw.split(":", 1)[-1].strip() or None
    return None


def _apply_voice_controls(text: str, jarvis: "JarvisLocal") -> bool:
    """Dynamic TTS volume commands. Returns True if consumed."""
    low = text.lower()
    from llm_client import get_settings, save_settings
    s = get_settings()
    if "raise your voice" in low or "speak louder" in low:
        s["tts_rate"] = min(300, int(s.get("tts_rate", 175)) + 25)
        save_settings(s)
        jarvis._speak("Voice raised.")
        return True
    if "lower your voice" in low or "speak quieter" in low:
        s["tts_rate"] = max(100, int(s.get("tts_rate", 175)) - 25)
        save_settings(s)
        jarvis._speak("Voice lowered.")
        return True
    if "mute yourself" in low and "unmute" not in low:
        s["speech_enabled"] = False
        save_settings(s)
        jarvis.ui.write_log("SYS: Speech disabled (microphone still available).")
        return True
    if "restore normal voice" in low or "unmute yourself" in low:
        s["speech_enabled"] = True
        save_settings(s)
        jarvis._speak("Speech restored.")
        return True
    return False


# ── Tool declarations (same schema as before, passed to Ollama) ───────────────
TOOL_DECLARATIONS = [
    {
        "name": "get_catchup",
        "description": "Retrieves the summary of the last session and recent conversation turns for context.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "save_task",
        "description": "Saves a new task to the database for tracking.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title of the task"},
                "description": {"type": "string", "description": "Detailed description"},
                "category": {"type": "string", "description": "work | personal | reminder | etc"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "market_tracker",
        "description": "Tracks stocks, manages watchlist, and opens broker sites.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "remove", "show_watchlist", "open_broker", "get_price"]},
                "symbol": {"type": "string"},
                "broker": {"type": "string"},
                "label":  {"type": "string"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":  {"type": "string",  "description": "Search query"},
                "mode":   {"type": "string",  "description": "search (default) or compare"},
                "items":  {"type": "array",   "items": {"type": "string"}, "description": "Items to compare"},
                "aspect": {"type": "string",  "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "object",
            "properties": {
                "receiver":     {"type": "string", "description": "Recipient contact name"},
                "message_text": {"type": "string", "description": "The message to send"},
                "platform":     {"type": "string", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "object",
            "properties": {
                "date":    {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "string", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "string", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "string", "description": "Search query for play action"},
                "save":   {"type": "boolean","description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "string", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "string", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "angle": {"type": "string", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "string", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action":      {"type": "string", "description": "The action to perform"},
                "description": {"type": "string", "description": "Natural language description of what to do"},
                "value":       {"type": "string", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action":      {"type": "string"},
                "browser":     {"type": "string"},
                "url":         {"type": "string"},
                "query":       {"type": "string"},
                "engine":      {"type": "string"},
                "selector":    {"type": "string"},
                "text":        {"type": "string"},
                "description": {"type": "string"},
                "direction":   {"type": "string"},
                "amount":      {"type": "integer"},
                "key":         {"type": "string"},
                "path":        {"type": "string"},
                "incognito":   {"type": "boolean"},
                "clear_first": {"type": "boolean"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "object",
            "properties": {
                "action":      {"type": "string"},
                "path":        {"type": "string"},
                "destination": {"type": "string"},
                "new_name":    {"type": "string"},
                "content":     {"type": "string"},
                "name":        {"type": "string"},
                "extension":   {"type": "string"},
                "count":       {"type": "integer"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "path":   {"type": "string"},
                "url":    {"type": "string"},
                "mode":   {"type": "string"},
                "task":   {"type": "string"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "object",
            "properties": {
                "action":      {"type": "string"},
                "description": {"type": "string"},
                "language":    {"type": "string"},
                "output_path": {"type": "string"},
                "file_path":   {"type": "string"},
                "code":        {"type": "string"},
                "args":        {"type": "string"},
                "timeout":     {"type": "integer"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "coding_bridge",
        "description": (
            "Local code edit/debug via Ollama or Aider CLI. "
            "Use for fixing bugs, patching files, and quick refactors in the repo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File to edit"},
                "instruction": {"type": "string", "description": "What to change or fix"},
                "use_aider": {"type": "boolean", "description": "Use Aider if installed"},
            },
            "required": ["file_path", "instruction"],
        },
    },
    {
        "name": "coding_agent",
        "description": (
            "Unified coding agent. Reads the screen for errors, finds the file, "
            "and fixes it using Aider or Ollama. Use for: fix this error, help me debug."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "What to fix"},
                "file_path": {"type": "string", "description": "File to edit (optional)"},
                "use_screen": {"type": "boolean", "description": "Capture screen (default true)"},
            },
            "required": [],
        },
    },
    {
        "name": "optimizely_agent",
        "description": (
            "Optimizely Configured Commerce expert. OCC/.NET errors, handlers, ElasticSearch, widgets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "ticket_id": {"type": "string", "description": "JIRA ticket ID"},
                "open_docs": {"type": "boolean", "description": "Open Optimizely docs"},
            },
            "required": [],
        },
    },
    {
        "name": "trading_briefing",
        "description": "Daily market news, watchlist prices, and AI trade recommendations.",
        "parameters": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "description": "Re-run if already briefed today"},
            },
        },
    },
    {
        "name": "self_upgrade",
        "description": (
            "Apply a self-upgrade: creates a git branch, writes changes, commits safely."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the upgrade does"},
                "search_github": {"type": "boolean", "description": "Search GitHub for ideas"},
                "github_query": {"type": "string", "description": "GitHub search query"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch.",
        "parameters": {
            "type": "object",
            "properties": {
                "description":  {"type": "string"},
                "language":     {"type": "string"},
                "project_name": {"type": "string"},
                "timeout":      {"type": "integer"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal":     {"type": "string"},
                "priority": {"type": "string"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "system_access",
        "description": (
            "Full system access: open ANY application (VS Code, Chrome, Outlook, Teams, etc), "
            "open folders in Explorer, run shell commands, read and write files, list directories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "open_app | open_folder | open_vscode | run | read | write | list"},
                "app_name": {"type": "string", "description": "Application name (VS Code, Chrome, Teams)"},
                "path": {"type": "string", "description": "File or folder path"},
                "folder": {"type": "string", "description": "Working directory"},
                "command": {"type": "string", "description": "Shell command to run"},
                "content": {"type": "string", "description": "Content to write to file"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots.",
        "parameters": {
            "type": "object",
            "properties": {
                "action":      {"type": "string"},
                "text":        {"type": "string"},
                "x":           {"type": "integer"},
                "y":           {"type": "integer"},
                "keys":        {"type": "string"},
                "key":         {"type": "string"},
                "direction":   {"type": "string"},
                "amount":      {"type": "integer"},
                "seconds":     {"type": "number"},
                "title":       {"type": "string"},
                "description": {"type": "string"},
                "type":        {"type": "string"},
                "field":       {"type": "string"},
                "clear_first": {"type": "boolean"},
                "path":        {"type": "string"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action":            {"type": "string"},
                "platform":          {"type": "string"},
                "game_name":         {"type": "string"},
                "app_id":            {"type": "string"},
                "hour":              {"type": "integer"},
                "minute":            {"type": "integer"},
                "shutdown_when_done":{"type": "boolean"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin":      {"type": "string"},
                "destination": {"type": "string"},
                "date":        {"type": "string"},
                "return_date": {"type": "string"},
                "passengers":  {"type": "integer"},
                "cabin":       {"type": "string"},
                "save":        {"type": "boolean"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis."
        ),
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "file_processor",
        "description": (
            "Processes any file that the user has uploaded or dropped onto the interface. "
            "Supports images, PDFs, Word docs, CSV/Excel, JSON/XML, code files, audio, video, archives."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string"},
                "action":      {"type": "string"},
                "instruction": {"type": "string"},
                "format":      {"type": "string"},
                "width":       {"type": "integer"},
                "height":      {"type": "integer"},
                "scale":       {"type": "number"},
                "quality":     {"type": "integer"},
                "start":       {"type": "string"},
                "end":         {"type": "string"},
                "timestamp":   {"type": "string"},
                "column":      {"type": "string"},
                "value":       {"type": "string"},
                "condition":   {"type": "string"},
                "ascending":   {"type": "boolean"},
                "save":        {"type": "boolean"},
                "destination": {"type": "string"},
            },
            "required": []
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call silently whenever the user reveals something worth remembering."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "key":      {"type": "string"},
                "value":    {"type": "string"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


# ── TTS engine (singleton, runs on its own thread) ────────────────────────────

class _TTSEngine:
    """Thread-safe pyttsx3 wrapper. pyttsx3 must run on the thread that created it."""

    def __init__(self):
        self._queue: list[str] = []
        self._lock  = threading.Lock()
        self._event = threading.Event()
        self._engine = None
        self._ready  = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        if not _TTS_OK:
            return
        try:
            self._engine = _pyttsx3.init()
            self._engine.setProperty("rate", 175)
            # pick a decent voice if available
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "david" in v.name.lower() or "mark" in v.name.lower() or "english" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
            self._ready = True
        except Exception as e:
            print(f"[TTS] Init failed: {e}")
            return

        while True:
            self._event.wait()
            self._event.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    item = self._queue.pop(0)
                if isinstance(item, tuple):
                    text, done_evt = item
                else:
                    text, done_evt = item, None
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                    print(f"[TTS] ✅ Spoke: {text[:60]}")
                except Exception as e:
                    print(f"[TTS] Speak error: {e}")
                finally:
                    if done_evt:
                        done_evt.set()

    def speak(self, text: str, wait: bool = False):
        if not _TTS_OK or not self._ready:
            print(f"[JARVIS] (no TTS) {text[:120]}")
            return
        done = threading.Event() if wait else None
        with self._lock:
            self._queue.append((text, done))
        self._event.set()
        if wait and done:
            done.wait(timeout=300)

    def stop(self):
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
        with self._lock:
            self._queue.clear()


_tts = _TTSEngine()


# ── VAD / mic recorder ────────────────────────────────────────────────────────

class _VoiceRecorder:
    """
    Listens on the mic, uses simple energy-based VAD.
    Calls on_utterance(audio_np) when a full utterance is detected.
    """

    def __init__(self, on_utterance, sample_rate: int = MIC_SAMPLE_RATE):
        self.on_utterance  = on_utterance
        self.sample_rate   = sample_rate
        self._muted        = False
        self._speaking     = False   # set True while JARVIS is playing TTS
        self._running      = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_muted(self, v: bool):
        self._muted = v

    def set_jarvis_speaking(self, v: bool):
        """Suppress mic input while JARVIS is talking (echo prevention)."""
        self._speaking = v

    def _loop(self):
        chunk_samples = int(self.sample_rate * CHUNK_DURATION)
        buf: list[np.ndarray] = []
        silence_chunks = 0
        in_speech = False
        required_silence = int(SILENCE_TIMEOUT / CHUNK_DURATION)

        def callback(indata, frames, time_info, status):
            nonlocal silence_chunks, in_speech
            if self._muted or self._speaking:
                return

            chunk = indata[:, 0].copy()
            rms   = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

            if rms > ENERGY_THRESHOLD:
                if not in_speech:
                    in_speech = True
                buf.append(chunk.copy())
                silence_chunks = 0
            elif in_speech:
                buf.append(chunk.copy())
                silence_chunks += 1
                if silence_chunks >= required_silence:
                    # end of utterance
                    audio = np.concatenate(buf)
                    buf.clear()
                    in_speech    = False
                    silence_chunks = 0
                    threading.Thread(
                        target=self.on_utterance,
                        args=(audio,),
                        daemon=True,
                    ).start()

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=MIC_CHANNELS,
                dtype=MIC_DTYPE,
                blocksize=chunk_samples,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while self._running:
                    import time; time.sleep(0.05)
        except Exception as e:
            print(f"[JARVIS] Mic error: {e}")


class _WakeWordListener:
    """Listens for 'Jarvis' or 'Wake up Jarvis' in the background."""
    def __init__(self, on_wake):
        self.on_wake = on_wake
        self._running = False
        self._thread = None
        self._recognizer = sr.Recognizer() if _SR_OK else None

    def start(self):
        if not _SR_OK: return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        with sr.Microphone() as source:
            self._recognizer.adjust_for_ambient_noise(source)
            while self._running:
                try:
                    # Listen for a short burst
                    audio = self._recognizer.listen(source, timeout=5, phrase_time_limit=3)
                    text = self._recognizer.recognize_google(audio).lower()
                    if any(w in text for w in ["jarvis", "wake up", "hey jarvis"]):
                        self.on_wake()
                except (sr.WaitTimeoutError, sr.UnknownValueError, sr.RequestError):
                    continue
                except Exception as e:
                    print(f"[WakeWord] Error: {e}")
                    time.sleep(1)

# ── Whisper STT ───────────────────────────────────────────────────────────────

_whisper_model = None
_whisper_lock  = threading.Lock()

def _get_whisper():
    global _whisper_model
    if not _WHISPER_OK:
        return None
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from llm_client import get_settings
                whisper_name = get_settings().get("whisper_model") or "base"
                print(f"[JARVIS] Loading Whisper model ({whisper_name})…")
                _whisper_model = _WhisperModel(whisper_name, device="cpu", compute_type="int8")
                print("[JARVIS] Whisper ready.")
            except Exception as e:
                print(f"[JARVIS] Whisper load failed: {e}")
        return _whisper_model


def _transcribe_with_confidence(audio_np: np.ndarray) -> tuple[str, float]:
    """Returns (text, avg_confidence). Confidence 0.0–1.0."""
    model = _get_whisper()
    if model is None:
        return "", 0.0
    try:
        from core.language import get_stt_language
        lang = get_stt_language()
        audio_f = audio_np.astype(np.float32) / 32768.0
        kwargs = {"beam_size": 3, "best_of": 3, "word_timestamps": True}
        if lang:
            kwargs["language"] = lang
        segments, _ = model.transcribe(audio_f, **kwargs)
        seg_list = list(segments)
        text = " ".join(seg.text for seg in seg_list).strip()
        if not seg_list:
            return text, 0.0
        confs = []
        for seg in seg_list:
            if seg.words:
                confs.append(sum(w.probability for w in seg.words) / len(seg.words))
            elif getattr(seg, "avg_logprob", None) is not None:
                confs.append(min(1.0, max(0.0, 1.0 + seg.avg_logprob / 5)))
            else:
                confs.append(0.7)
        return text, sum(confs) / len(confs)
    except Exception as e:
        print(f"[JARVIS] Transcription error: {e}")
        return "", 0.0


def _transcribe(audio_np: np.ndarray) -> str:
    text, _ = _transcribe_with_confidence(audio_np)
    return text


# ── Main assistant class ──────────────────────────────────────────────────────

import queue

class JarvisLocal:

    def __init__(self, ui: JarvisUI):
        self.ui            = ui
        self._history: list[dict] = []   # conversation history for Ollama
        self._lock         = threading.Lock()
        self._recorder     = _VoiceRecorder(self._on_raw_audio)
        self.interrupt_event = threading.Event()
        self._wake_listener = _WakeWordListener(self._on_wake)
        self._last_interaction = time.time()
        self._idle_timer_running = False
        self._greeting_step = 0  # 0 = normal; 2–5 = permission gates
        self._idle_prompt_step = 0  # 0 = off; 1 = waiting yes/no to minimize
        self._skip_prefix_once = False  # after wake word, next utterance skips prefix
        self._processing = False
        self._process_lock = threading.Lock()
        self._pending_confirmation: str | None = None

        # Mini HUD companion window
        try:
            from ui.mini_hud import get_mini_hud
            self._mini_hud = get_mini_hud()
            self._mini_hud.send_command.connect(self._on_mini_hud_command)
        except Exception as e:
            print(f"[MiniHUD] Init failed: {e}")
            self._mini_hud = None

        # Task 13: TTS Queue
        self._tts_queue = queue.Queue()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

        # wire up UI text command
        self.ui.on_text_command = self._on_text_command
        self.ui.on_close = self._on_close
        self.ui.on_mute_changed = self._on_mute_changed
        self.ui.on_window_shown = self._on_window_shown
        self.ui.on_window_hidden = self._on_window_hidden

    def _on_window_shown(self):
        """Window visible: voice recorder on, wake word off."""
        self._last_interaction = time.time()
        self._wake_listener.stop()
        self._recorder.start()
        if self._mini_hud:
            self._mini_hud.hide()

    def _on_window_hidden(self):
        """Window hidden: voice recorder off, wake word on."""
        self._recorder.stop()
        if _SR_OK:
            self._wake_listener.start()
        if self._mini_hud:
            self._mini_hud.show()
            self._mini_hud.raise_()

    def _on_mini_hud_command(self, cmd: str):
        if cmd == "__restore_main__":
            self.ui.show()
            if self._mini_hud:
                self._mini_hud.hide()
        else:
            self._on_text_command(cmd)

    def _handle_pending_confirmation(self, text: str) -> bool:
        if not self._pending_confirmation:
            return False
        if _is_yes(text):
            confirmed = self._pending_confirmation
            self._pending_confirmation = None
            threading.Thread(target=self._process, args=(confirmed,), daemon=True).start()
            return True
        if _is_no(text):
            self._pending_confirmation = None
            self._speak("Okay, say it again clearly.")
            return True
        return False

    def _tts_worker(self):
        """Dedicated TTS thread. Mic mute does NOT affect TTS."""
        while True:
            text = self._tts_queue.get()
            try:
                if not _speech_enabled():
                    print(f"[TTS] SKIPPED (speech_enabled=False): {text[:60]}")
                    self._tts_queue.task_done()
                    continue

                self.ui.set_state("SPEAKING")
                self._recorder.set_jarvis_speaking(True)
                spoken = _tts_sanitize(text)
                if not spoken:
                    print(f"[TTS] SKIPPED (empty after sanitize): {repr(text[:60])}")
                    self._recorder.set_jarvis_speaking(False)
                    self.ui.set_state("LISTENING")
                    self._tts_queue.task_done()
                    continue

                print(f"[TTS] Speaking: {spoken[:80]}")
                spoke = False
                try:
                    _tts.speak(spoken, wait=True)
                    spoke = True
                except Exception as e1:
                    print(f"[TTS] Primary failed: {e1}")

                if not spoke:
                    try:
                        import pyttsx3
                        engine = pyttsx3.init()
                        engine.setProperty("rate", 175)
                        engine.say(spoken)
                        engine.runAndWait()
                        engine.stop()
                        spoke = True
                    except Exception as e2:
                        print(f"[TTS] Fallback pyttsx3 failed: {e2}")

                if not spoke:
                    try:
                        import subprocess
                        safe = spoken[:200].replace('"', " ").replace("\n", " ")
                        script = (
                            "Add-Type -AssemblyName System.Speech; "
                            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                            f'$s.Speak("{safe}")'
                        )
                        subprocess.Popen(
                            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        spoke = True
                        print("[TTS] Used PowerShell SAPI fallback")
                    except Exception as e3:
                        print(f"[TTS] All TTS methods failed: {e3}")

            except Exception as outer:
                print(f"[TTS] Worker outer error: {outer}")
            finally:
                self._recorder.set_jarvis_speaking(False)
                time.sleep(0.25)
                self.ui.set_state("LISTENING")
                self._tts_queue.task_done()

    def _on_mute_changed(self, muted: bool):
        """Mic mute only — stops listener, not TTS or background agents."""
        self._recorder.set_muted(muted)
        try:
            from db.database import set_preference
            set_preference("mic_muted", str(muted))
        except Exception:
            pass

    def _on_close(self):
        """Task 12.4: Save session summary on close."""
        from memory.memory_manager import generate_session_summary
        summary = generate_session_summary(self._history)
        try:
            conn = get_db()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            # Find the active session and close it
            cursor.execute("UPDATE sessions SET ended_at = ?, summary = ? WHERE ended_at IS NULL", (now, summary))
            conn.commit()
            conn.close()
        except Exception: pass

    # ── public start ─────────────────────────────────────────────────
    def start(self):
        if _jarvis_log:
            _jarvis_log.info("JarvisLocal.start()")
        threading.Thread(target=self._run_diagnostics_background, daemon=True).start()
        try:
            from core.hardware_profile import apply_hardware_model_async
            apply_hardware_model_async(on_log=lambda m: self.ui.write_log(f"SYS: {m}"))
        except Exception as e:
            print(f"[Hardware] {e}")
        warm_up_model()
        
        model_info = get_active_model()
        self.ui.write_log(
            f"SYS: JARVIS online — {model_info['provider']} / {model_info['model']}"
        )
        self.ui.set_state("LISTENING")
        self._start_idle_timer()
        
        print(f"[JARVIS] ✅ Started. Model: {model_info}")
        
        from llm_client import get_settings
        settings = get_settings()
        if settings.get("run_greeting", True):
            threading.Thread(target=self._run_greeting, daemon=True).start()
        else:
            self.ui.write_log("SYS: Ready.")

        # Keep window visible by default so dashboard + mic stay usable
        if not settings.get("first_launch_complete"):
            settings["first_launch_complete"] = True
            from llm_client import save_settings
            save_settings(settings)

        self.ui.show()
        self.ui._jarvis_ref = self
        if hasattr(self.ui._win, "_dash"):
            self.ui._win._dash.show()
            self.ui._win._refresh_side()

        if settings.get("start_minimized", False):
            self.ui.write_log("SYS: Starting in tray — use tray menu Show to open.")
            threading.Timer(3.0, self.ui.hide).start()
        else:
            self.ui.write_log("SYS: Microphone active. Say Jarvis or type commands.")

    def _run_greeting(self):
        """Step 1 greeting, then permission-gated steps 2–5."""
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        else:
            period = "evening"

        tasks = get_active_tasks()
        seen: set[str] = set()
        unique_tasks = []
        for t in tasks:
            title = (t.get("title") or "").strip()
            if title and title.lower() not in seen:
                seen.add(title.lower())
                unique_tasks.append(t)
        model_name = get_active_model()["model"]
        line = (
            f"Good {period}, SS. Today is {now.strftime('%A, %B %d')}. "
            f"The time is {now.strftime('%I:%M %p')}. "
            f"I'm running on {model_name}."
        )
        if unique_tasks:
            line += f" You have {len(unique_tasks)} active task{'s' if len(unique_tasks) != 1 else ''} from your last session."
        line += " What would you like to do?"

        self.ui.write_log(f"Jarvis: {line}")
        self._speak(line)
        add_session(now.isoformat(), summary="Started session")
        if hasattr(self.ui._win, "_refresh_side"):
            self.ui._win._refresh_side()

        try:
            from actions.trading_agent import is_first_wake_today, trading_briefing
            if is_first_wake_today():
                threading.Thread(
                    target=trading_briefing,
                    kwargs={"parameters": {}, "player": self.ui, "speak": self._speak},
                    daemon=True,
                ).start()
        except Exception as e:
            print(f"[Trading] Briefing error: {e}")

        from llm_client import get_settings
        if not get_settings().get("run_greeting", True):
            return
        if not get_settings().get("run_greeting_steps", False):
            return

        self._greeting_step = 2
        time.sleep(0.8)
        self._greeting_ask("Should I pull today's weather?")

    def _greeting_ask(self, question: str):
        self.ui.write_log(f"Jarvis: {question}")
        self._speak(question)

    def _handle_greeting_reply(self, text: str) -> bool:
        """Handle yes/no during startup permission sequence. Returns True if consumed."""
        if self._greeting_step == 0:
            return False
        if _is_skip_all(text) or _is_real_command(text):
            self._greeting_step = 0
            if _is_skip_all(text):
                self._speak("Understood. I'm listening, SS.")
            if hasattr(self.ui._win, "_refresh_side"):
                self.ui._win._refresh_side()
            return _is_skip_all(text)

        step = self._greeting_step
        yes, no = _is_yes(text), _is_no(text)
        if not yes and not no:
            return False

        if step == 2:
            if yes:
                try:
                    from llm_client import get_settings
                    city = get_settings().get("weather_city") or "Chennai"
                    from services.weather_service import format_weather_line
                    w = format_weather_line(city)
                    self.ui.write_log(f"Jarvis: {w}")
                    self._speak(w[:200])
                except Exception as e:
                    self.ui.write_log(f"Jarvis: Could not fetch weather — {e}")
            self._greeting_step = 3 if not no else 0
            if self._greeting_step == 3:
                self._greeting_ask("Want me to open Groww and check your watchlist?")
            else:
                self._speak("I'm listening, SS.")
            return True

        if step == 3:
            if yes:
                try:
                    from actions.browser_control import browser_control
                    browser_control({"action": "open", "url": "https://groww.in"})
                    from actions.market_tracker import run as market_tracker
                    r = market_tracker({"action": "show_watchlist"})
                    self.ui.write_log(f"Jarvis: {r}")
                    self._speak(str(r)[:180])
                except Exception as e:
                    self.ui.write_log(f"Jarvis: {e}")
            self._greeting_step = 4 if not no else 0
            if self._greeting_step == 4:
                self._greeting_ask("Should I get a quick world news summary?")
            else:
                self._speak("I'm listening, SS.")
            return True

        if step == 4:
            if yes:
                try:
                    r = web_search_action({"query": "world news today"})
                    summary = str(r)[:500]
                    self.ui.write_log(f"Jarvis: {summary}")
                    self._speak(summary[:200])
                except Exception as e:
                    self.ui.write_log(f"Jarvis: News unavailable — {e}")
            self._greeting_step = 5 if not no else 0
            if self._greeting_step == 5:
                self._greeting_ask("Want me to recap your pending tasks?")
            else:
                self._speak("I'm listening, SS.")
            return True

        if step == 5:
            if yes:
                tasks = get_active_tasks()
                seen: set[str] = set()
                titles = []
                for t in tasks:
                    title = (t.get("title") or "").strip()
                    if title and title.lower() not in seen:
                        seen.add(title.lower())
                        titles.append(title)
                if titles:
                    lines = "; ".join(titles[:8])
                    self.ui.write_log(f"Jarvis: Active tasks: {lines}")
                    self._speak(f"You have {len(titles)} tasks. {lines[:200]}")
                else:
                    self._speak("You have no active tasks.")
            elif no and hasattr(self.ui._win, "_refresh_side"):
                self.ui._win._refresh_side()
            self._greeting_step = 0
            self._speak("I'm listening, SS.")
            return True

        return False

    def _run_diagnostics_background(self):
        try:
            from diagnostics.system_diagnostics import run_diagnostics
            report = run_diagnostics()
            fails = [k for k, v in report.items() if not v.get("ok")]
            if fails and _jarvis_log:
                _jarvis_log.warning("Diagnostics issues: %s", fails)
        except Exception as e:
            if _jarvis_log:
                _jarvis_log.debug("Diagnostics skipped: %s", e)

    def _on_wake(self):
        """Called when wake word is detected."""
        print("[JARVIS] 🔔 Wake word detected!")
        self._last_interaction = time.time()
        self._skip_prefix_once = True
        
        # 1. Restore window (starts recorder via on_window_shown)
        self.ui.show()
        
        # 2. Play chime
        try:
            winsound.Beep(1000, 200)
            winsound.Beep(1200, 200)
        except Exception:
            pass
            
        # 3. Say "I'm listening"
        self._speak("I'm listening, SS.")
        
        # 4. Flash mic indicator (already handled by set_state LISTENING which is called in _speak)
        self.ui.set_state("LISTENING")

    def _start_idle_timer(self):
        if self._idle_timer_running:
            return
        self._idle_timer_running = True

        def _timer():
            while True:
                time.sleep(5)
                idle_sec = time.time() - self._last_interaction
                if idle_sec < 300:
                    continue
                if not self.ui._win.isVisible() or self.ui.state != "LISTENING":
                    continue
                if self._processing or self._idle_prompt_step:
                    continue
                print("[JARVIS] 💤 Idle — asking permission to minimize…")
                self._idle_prompt_step = 1
                self.ui.write_log("Jarvis: SS, should I go idle and minimize? Say yes or no.")
                self._speak("SS, should I go idle and minimize? Say yes or no.")

        threading.Thread(target=_timer, daemon=True).start()

    def _handle_idle_reply(self, text: str) -> bool:
        if self._idle_prompt_step != 1:
            return False
        yes, no = _is_yes(text), _is_no(text)
        if not yes and not no:
            return False
        self._idle_prompt_step = 0
        self._last_interaction = time.time()
        if yes:
            self._speak("Going quiet. Say wake up Jarvis when you need me.")
            threading.Timer(1.2, self.ui.hide).start()
        else:
            self._speak("Staying on, SS.")
        return True

    def _do_stop(self):
        """Cancel current work — only path that interrupts Jarvis."""
        print("[JARVIS] ⏹ Stop requested")
        self.interrupt_event.set()
        _tts.stop()
        with self._process_lock:
            self._processing = False
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except Exception:
                break
        self.ui.write_log("Jarvis: Stopped.")
        self._speak("Stopped, SS.")
        self.ui.set_state("LISTENING")

    # ── voice path ───────────────────────────────────────────────────
    def _on_raw_audio(self, audio_np: np.ndarray):
        """Called from recorder thread when an utterance is captured."""
        if self.ui.muted:
            return

        text, confidence = _transcribe_with_confidence(audio_np)
        if not text or len(text.strip()) < 3:
            return

        if _is_stop_command(text):
            self._last_interaction = time.time()
            self._do_stop()
            return

        if self._handle_pending_confirmation(text):
            return

        if self._processing or self.ui.state in ("SPEAKING", "THINKING", "PROCESSING"):
            return

        LOW_CONFIDENCE = 0.55
        if confidence < LOW_CONFIDENCE and not _is_stop_command(text):
            self.ui.write_log(f"[?] Did you say: \"{text}\" ? (say yes/no or repeat)")
            self._speak(f"Did you say: {text}?")
            self._pending_confirmation = text
            return

        self._pending_confirmation = None
        self._last_interaction = time.time()
        self.ui.set_state("THINKING")
        if not self._skip_prefix_once:
            cmd = _parse_voice_command(text)
            if cmd is None:
                self.ui.set_state("LISTENING")
                return
            text = cmd
        else:
            self._skip_prefix_once = False

        if _apply_voice_controls(text, self):
            self.ui.set_state("LISTENING")
            return

        self.ui.write_log(f"You: {text}")
        if self._handle_idle_reply(text):
            self.ui.set_state("LISTENING")
            return
        if _try_fast_command(text, self):
            self.ui.set_state("LISTENING")
            return
        if self._handle_greeting_reply(text):
            self.ui.set_state("LISTENING")
            return
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    # ── text path (from input box) ────────────────────────────────────
    def _on_text_command(self, text: str):
        self._last_interaction = time.time()
        if _is_stop_command(text):
            self._do_stop()
            return
        if self._handle_pending_confirmation(text):
            return
        if self._handle_idle_reply(text):
            return
        if _try_fast_command(text, self):
            return
        if self._handle_greeting_reply(text):
            return
        if self._processing:
            self.ui.write_log("SYS: Still working — say 'Jarvis stop' to cancel.")
            return
        self.ui.set_state("THINKING")
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    # ── core processing ───────────────────────────────────────────────
    def _process(self, user_text: str):
        """Send user_text to Ollama, handle tool calls, speak reply."""
        with self._process_lock:
            if self._processing:
                self.ui.write_log("SYS: Still working — say 'Jarvis stop' to cancel.")
                return
            self._processing = True
        self.interrupt_event.clear()
        if _try_fast_command(user_text, self):
            self.ui.set_state("LISTENING")
            with self._process_lock:
                self._processing = False
            return
        try:
            self.ui.set_state("PROCESSING")
            log_conversation("user", user_text)
            system_prompt = self._build_system_prompt(user_text)

            with self._lock:
                self._history.append({"role": "user", "content": user_text})
                messages = list(self._history)

            self.ui.set_state("THINKING")
            
            # BUG 1 Fix: Use streaming
            resp = chat_with_tools(
                messages=messages,
                tools=TOOL_DECLARATIONS,
                system_prompt=system_prompt,
                stream=True
            )

            full_content = ""
            tool_calls = []
            
            self.ui.write_log_no_type("Jarvis: ") # Start the AI log entry
            
            if hasattr(resp, "iter_lines"): # Streaming response
                for line in resp.iter_lines():
                    if self.interrupt_event.is_set():
                        print("[JARVIS] ⏹ Stream stopped")
                        self.ui.write_log("Jarvis: Stopped.")
                        return
                    
                    if not line: continue
                    chunk = json.loads(line.decode("utf-8"))
                    
                    if "message" in chunk:
                        delta = chunk["message"].get("content", "")
                        if delta:
                            full_content += delta
                            self.ui.stream_chunk(delta)
                        
                        if "tool_calls" in chunk["message"]:
                            tool_calls.extend(chunk["message"]["tool_calls"])
                    
                    if chunk.get("done"):
                        break
            else: # Non-streaming fallback
                msg = resp.get("message", {})
                full_content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls", [])
                if full_content:
                    self.ui.stream_chunk(full_content)

            if tool_calls:
                # execute each tool call sequentially
                tool_results = []
                for tc in tool_calls:
                    if self.interrupt_event.is_set(): break
                    
                    fn   = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    print(f"[JARVIS] 🔧 {name}  {args}")
                    self.ui.set_state("THINKING")
                    result = self._execute_tool(name, args)
                    tool_results.append({
                        "role": "tool",
                        "content": str(result),
                        "name": name,
                    })

                if not self.interrupt_event.is_set():
                    # send tool results back so Ollama can formulate a reply
                    with self._lock:
                        self._history.append({"role": "assistant", "content": full_content, "tool_calls": tool_calls})
                        self._history.extend(tool_results)
                        messages2 = list(self._history)

                    resp2 = chat_with_tools(
                        messages=messages2,
                        tools=TOOL_DECLARATIONS,
                        system_prompt=system_prompt,
                        stream=True
                    )
                    
                    final_reply = ""
                    if hasattr(resp2, "iter_lines"):
                        for line in resp2.iter_lines():
                            if self.interrupt_event.is_set(): break
                            if not line: continue
                            chunk = json.loads(line.decode("utf-8"))
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                final_reply += delta
                                self.ui.stream_chunk(delta)
                            if chunk.get("done"): break
                    else:
                        final_reply = resp2.get("message", {}).get("content", "") or ""
                        if final_reply:
                            self.ui.stream_chunk(final_reply)
                    
                    full_content = final_reply

            # trim history to last 20 turns to keep context manageable
            with self._lock:
                self._history.append({"role": "assistant", "content": full_content})
                if len(self._history) > 40:
                    self._history = self._history[-40:]

            if full_content and not self.interrupt_event.is_set():
                self.ui.stream_chunk("\n")
                log_conversation("assistant", full_content)
                self._speak(full_content)
            else:
                self.ui.set_state("LISTENING")

        except Exception as e:
            err = str(e)
            print(f"[JARVIS] ❌ Process error: {err}")
            if _jarvis_log:
                _jarvis_log.exception("Process error")
            traceback.print_exc()
            self.ui.write_log(f"ERR: {err[:120]}")
            hint = "Try a shorter question or check Ollama is running."
            if "timed out" in err.lower():
                hint = "Ollama timed out. Use a smaller model or wait for warm-up to finish."
            self.ui.write_log(f"SYS: {hint}")
            self._speak(f"SS, I hit an error. {hint}")
        finally:
            with self._process_lock:
                self._processing = False
            if self.ui.state in ("PROCESSING", "THINKING"):
                self.ui.set_state("LISTENING")

    # ── TTS output ────────────────────────────────────────────────────
    def _speak(self, text: str):
        if text and _speech_enabled():
            if self._mini_hud:
                self._mini_hud.set_text(text[:100])
            self._tts_queue.put(text)

    # ── system prompt ─────────────────────────────────────────────────
    def _build_system_prompt(self, user_text: str = "") -> str:
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        base    = _load_system_prompt()
        now     = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
        parts   = [
            f"[CURRENT DATE & TIME]\nRight now it is: {now}\n",
        ]
        if mem_str:
            parts.append(mem_str)
        parts.append(base)
        try:
            from core.language import prompt_instruction
            parts.append(prompt_instruction())
        except ImportError:
            pass
        merged = "\n\n".join(parts)
        try:
            from agent.orchestrator import enrich_system_prompt
            merged = enrich_system_prompt(merged, user_text)
        except ImportError:
            pass
        knowledge_dir = BASE_DIR / "knowledge" / "optimizely"
        occ_parts = []
        for fname in ["README.md", "PATTERNS.md"]:
            f = knowledge_dir / fname
            if f.exists():
                try:
                    occ_parts.append(f.read_text(encoding="utf-8")[:3000])
                except Exception:
                    pass

        try:
            from llm_client import get_settings as _gs
            occ_path_str = (_gs().get("coding") or {}).get("optimizely_path", "")
            if occ_path_str:
                from pathlib import Path as _P
                occ_root = _P(occ_path_str)
                if occ_root.exists():
                    cs_files = sorted(
                        occ_root.rglob("*.cs"),
                        key=lambda f: (
                            0 if "Handler" in f.name else
                            1 if "Service" in f.name else
                            2 if "Controller" in f.name else 3
                        ),
                    )[:6]
                    for cf in cs_files:
                        try:
                            content = cf.read_text(encoding="utf-8", errors="ignore")[:2500]
                            occ_parts.append(f"[OCC FILE: {cf.name}]\n{content}")
                        except Exception:
                            pass
                    merged += f"\n\n[OPTIMIZELY PROJECT PATH]: {occ_path_str}"
        except Exception:
            pass

        if occ_parts:
            merged += "\n\n[OPTIMIZELY CONTEXT]\n" + "\n\n".join(occ_parts)
            merged += (
                "\n\nYou are an expert in Optimizely Configured Commerce (.NET, ElasticSearch, React, IIS, SQL Server). "
                "When asked about this project, use the actual file content above."
            )
        return merged

    # ── tool executor ─────────────────────────────────────────────────
    def _execute_tool(self, name: str, args: dict) -> Any:
        ui = self.ui
        from ui.activity_panel import activity_start, activity_update, activity_end
        detail = ", ".join(f"{k}={v}" for k, v in list((args or {}).items())[:3])
        activity_start(name, detail)

        try:
            result = self._execute_tool_inner(name, args or {})
            activity_update(str(result)[:120] if result else "done")
            return result
        finally:
            activity_end()

    def _execute_tool_inner(self, name: str, args: dict) -> Any:
        ui = self.ui

        try:
            if name == "get_catchup":
                from memory.memory_manager import get_session_catchup
                return get_session_catchup()

            if name == "save_task":
                title = args.get("title")
                desc = args.get("description", "")
                cat = args.get("category", "personal")
                try:
                    save_task(title, desc, cat)
                    if hasattr(ui._win, "_refresh_side"):
                        ui._win._refresh_side()
                    return f"Task '{title}' saved successfully."
                except Exception as e:
                    return f"Failed to save task: {e}"

            elif name == "save_memory":
                category = args.get("category", "notes")
                key      = args.get("key", "")
                value    = args.get("value", "")
                if key and value:
                    update_memory({category: {key: {"value": value}}})
                    print(f"[Memory] 💾 {category}/{key} = {value}")
                return "ok"

            elif name == "market_tracker":
                result = market_tracker(parameters=args, player=ui) or "Market data retrieved."
                try:
                    if hasattr(ui, "_win") and hasattr(ui._win, "_refresh_side"):
                        ui._win._refresh_side()
                except Exception:
                    pass
                return result

            elif name == "open_app":
                return open_app(parameters=args, response=None, player=ui) or f"Opened {args.get('app_name')}."

            elif name == "system_access":
                from actions.system_access import system_access
                return system_access(args, player=ui, speak=self._speak) or "Done."

            elif name == "weather_report":
                return weather_action(parameters=args, player=ui) or "Weather delivered."

            elif name == "browser_control":
                return browser_control(parameters=args, player=ui) or "Done."

            elif name == "file_controller":
                return file_controller(parameters=args, player=ui) or "Done."

            elif name == "send_message":
                return send_message(parameters=args, response=None, player=ui, session_memory=None) or "Message sent."

            elif name == "reminder":
                return reminder(parameters=args, response=None, player=ui) or "Reminder set."

            elif name == "youtube_video":
                return youtube_video(parameters=args, response=None, player=ui) or "Done."

            elif name == "screen_process":
                return screen_process(parameters=args, player=ui, speak=self._speak) or "Analysis complete."

            elif name == "computer_settings":
                return computer_settings(parameters=args, response=None, player=ui) or "Done."

            elif name == "desktop_control":
                return desktop_control(parameters=args, player=ui) or "Done."

            elif name == "code_helper":
                return code_helper(parameters=args, player=ui, speak=self._speak) or "Done."

            elif name == "coding_bridge":
                from actions.coding_bridge import coding_bridge
                return coding_bridge(parameters=args, player=ui, speak=self._speak) or "Done."

            elif name == "coding_agent":
                from actions.coding_agent import coding_agent
                return coding_agent(args, player=ui, speak=self._speak) or "Done."

            elif name == "optimizely_agent":
                from actions.optimizely_agent import optimizely_agent
                return optimizely_agent(args, player=ui, speak=self._speak) or "Done."

            elif name == "trading_briefing":
                from actions.trading_agent import trading_briefing
                return trading_briefing(args, player=ui, speak=self._speak) or "Done."

            elif name == "self_upgrade":
                from self_upgrade.upgrade_manager import self_upgrade_tool
                return self_upgrade_tool(args, player=ui, speak=self._speak) or "Done."

            elif name == "dev_agent":
                description = args.get("description", "")
                if any(x in description.lower() for x in ["tool", "feature", "capability"]):
                    # Self-building mode
                    from actions.dev_agent import build_jarvis_tool
                    tool_info = build_jarvis_tool(description, speak=self._speak, player=ui)
                    if tool_info:
                        # Dynamically register the new tool
                        try:
                            module_name = f"actions.{tool_info['name']}"
                            # Clear from cache if exists
                            if module_name in sys.modules:
                                del sys.modules[module_name]
                            
                            module = importlib.import_module(module_name)
                            if hasattr(module, "TOOL_SPEC") and hasattr(module, "run"):
                                # Add to global declarations
                                TOOL_DECLARATIONS.append(module.TOOL_SPEC)
                                # Confirmation
                                msg = f"Done. I've created {tool_info['name']} and it's ready to use right now."
                                ui.write_log(f"SYS: Registered new tool: {tool_info['name']}")
                                self._speak(msg)
                                
                                # Store as task in DB
                                try:
                                    conn = get_db()
                                    cursor = conn.cursor()
                                    now = datetime.now().isoformat()
                                    cursor.execute(
                                        "INSERT INTO tasks (created_at, updated_at, title, description, category) VALUES (?, ?, ?, ?, ?)",
                                        (now, now, f"Built tool: {tool_info['name']}", description, "self_built_tool")
                                    )
                                    conn.commit()
                                    conn.close()
                                except Exception as dbe:
                                    print(f"[DB] Error saving tool task: {dbe}")
                                
                                return msg
                        except Exception as e:
                            return f"Tool built but registration failed: {e}"
                    return "Tool building failed."
                else:
                    return dev_agent(parameters=args, player=ui, speak=self._speak) or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {
                    "low":    TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high":   TaskPriority.HIGH,
                }
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self._speak)
                return f"Task started (ID: {task_id})."

            elif name == "web_search":
                return web_search_action(parameters=args, player=ui) or "Done."

            elif name == "file_processor":
                if not args.get("file_path") and ui.current_file:
                    args["file_path"] = ui.current_file
                return file_processor(parameters=args, player=ui, speak=self._speak) or "Done."

            elif name == "computer_control":
                return computer_control(parameters=args, player=ui) or "Done."

            elif name == "game_updater":
                return game_updater(parameters=args, player=ui, speak=self._speak) or "Done."

            elif name == "flight_finder":
                return flight_finder(parameters=args, player=ui) or "Done."

            elif name == "shutdown_jarvis":
                ui.write_log("SYS: Shutdown requested.")
                self._speak("Goodbye, sir.")
                import time, os
                def _exit():
                    time.sleep(1.5)
                    os._exit(0)
                threading.Thread(target=_exit, daemon=True).start()
                return "Shutting down."

            else:
                return f"Unknown tool: {name}"

        except Exception as e:
            traceback.print_exc()
            return f"Tool '{name}' failed: {e}"


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    init_db()
    try:
        ensure_runtime_dirs()
    except NameError:
        pass

    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLocal(ui)
        jarvis.start()
        while True:
            time.sleep(1)

    threading.Thread(target=runner, daemon=True).start()
    sys.exit(ui._app.exec())


if __name__ == "__main__":
    main()