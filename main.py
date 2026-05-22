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
from ui import JarvisUI
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
        "You are Mark-XXXIX, a personal AI assistant for SS. "
        "Be concise and direct. Use tools when needed. Ask before external actions."
    )


def _is_yes(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in ("yes", "yeah", "yep", "sure", "ok", "okay", "please", "do it", "go ahead"))


def _is_no(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in ("no", "nope", "don't", "skip", "not now", "later"))


def _is_skip_all(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in ("skip all", "just start", "skip everything", "start listening"))


def _speech_enabled() -> bool:
    try:
        from llm_client import get_settings
        return bool(get_settings().get("speech_enabled", True))
    except Exception:
        return True


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
        if not get_settings().get("require_jarvis_prefix", True):
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
                "action": {"type": "string", "enum": ["add", "show_watchlist", "open_broker", "get_price"]},
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
                    text = self._queue.pop(0)
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e:
                    print(f"[TTS] Speak error: {e}")

    def speak(self, text: str):
        if not _TTS_OK or not self._ready:
            print(f"[JARVIS] (no TTS) {text}")
            return
        with self._lock:
            self._queue.append(text)
        self._event.set()

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
                print("[JARVIS] Loading Whisper model (base.en)…")
                _whisper_model = _WhisperModel("base.en", device="cpu", compute_type="int8")
                print("[JARVIS] Whisper ready.")
            except Exception as e:
                print(f"[JARVIS] Whisper load failed: {e}")
        return _whisper_model


def _transcribe(audio_np: np.ndarray) -> str:
    model = _get_whisper()
    if model is None:
        return ""
    try:
        # faster-whisper expects float32 normalised to [-1, 1]
        audio_f = audio_np.astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio_f, language="en", beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        print(f"[JARVIS] Transcription error: {e}")
        return ""


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
        self._skip_prefix_once = False  # after wake word, next utterance skips prefix

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

    def _on_window_hidden(self):
        """Window hidden: voice recorder off, wake word on."""
        self._recorder.stop()
        if _SR_OK:
            self._wake_listener.start()

    def _tts_worker(self):
        """Dedicated thread for speaking from a queue. Mic mute does NOT block TTS."""
        while True:
            text = self._tts_queue.get()
            if not _speech_enabled():
                self._tts_queue.task_done()
                continue
                
            self.ui.set_state("SPEAKING")
            self._recorder.set_jarvis_speaking(True)
            try:
                _tts.speak(text)
            except Exception as e:
                print(f"[JARVIS] Primary TTS failed, using fallback: {e}")
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.say(text)
                    engine.runAndWait()
                except Exception as e2:
                    print(f"[JARVIS] Fallback TTS also failed: {e2}")
            
            self._recorder.set_jarvis_speaking(False)
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

        if settings.get("first_launch_complete", False) and settings.get("start_minimized", True):
            self.ui.hide()
        else:
            settings["first_launch_complete"] = True
            from llm_client import save_settings
            save_settings(settings)

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
        model_name = get_active_model()["model"]
        line = (
            f"Good {period}, SS. Today is {now.strftime('%A, %B %d')}. "
            f"The time is {now.strftime('%I:%M %p')}. "
            f"I'm running on {model_name}."
        )
        if tasks:
            line += f" You have {len(tasks)} active tasks from your last session."
        line += " What would you like to do?"

        self.ui.write_log(f"Jarvis: {line}")
        self._speak(line)
        add_session(now.isoformat(), summary="Started session")
        if hasattr(self.ui._win, "_refresh_side"):
            self.ui._win._refresh_side()

        from llm_client import get_settings
        if not get_settings().get("run_greeting", True):
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
        if _is_skip_all(text):
            self._greeting_step = 0
            self._speak("Understood. I'm listening, SS.")
            if hasattr(self.ui._win, "_refresh_side"):
                self.ui._win._refresh_side()
            return True

        step = self._greeting_step
        yes, no = _is_yes(text), _is_no(text)

        if step == 2:
            if yes:
                try:
                    from llm_client import get_settings
                    city = get_settings().get("weather_city") or "current location"
                    from actions.weather_report import weather_action
                    w = weather_action({"city": city})
                    self.ui.write_log(f"Jarvis: {w[:400]}")
                    self._speak(w[:200])
                except Exception as e:
                    self.ui.write_log(f"Jarvis: Could not fetch weather — {e}")
            self._greeting_step = 3
            self._greeting_ask("Want me to open Groww and check your watchlist?")
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
            self._greeting_step = 4
            self._greeting_ask("Should I get a quick world news summary?")
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
            self._greeting_step = 5
            self._greeting_ask("Want me to recap your pending tasks?")
            return True

        if step == 5:
            if yes:
                tasks = get_active_tasks()
                if tasks:
                    lines = "; ".join(t["title"] for t in tasks[:8])
                    self.ui.write_log(f"Jarvis: Active tasks: {lines}")
                    self._speak(f"You have {len(tasks)} tasks. {lines[:200]}")
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
        if self._idle_timer_running: return
        self._idle_timer_running = True
        def _timer():
            while True:
                time.sleep(5)
                if time.time() - self._last_interaction > 90:
                    if self.ui._win.isVisible() and self.ui.state == "LISTENING":
                        print("[JARVIS] 💤 Idle for 90s, minimizing...")
                        self._speak("Going quiet. Say Wake up Jarvis when you need me.")
                        self.ui.hide()
        threading.Thread(target=_timer, daemon=True).start()

    # ── voice path ───────────────────────────────────────────────────
    def _on_raw_audio(self, audio_np: np.ndarray):
        """Called from recorder thread when an utterance is captured."""
        if self.ui.muted:
            return
        
        self._last_interaction = time.time()
        
        # TASK 4 Fix: Handle interruption
        if self.ui.state in ("THINKING", "SPEAKING", "PROCESSING"):
            print("[JARVIS] ✋ Interrupted by voice!")
            self.interrupt_event.set()
            _tts.stop()
            self.ui.write_log("Jarvis: [cancelled — interrupted]")
        
        self.ui.set_state("THINKING")
        text = _transcribe(audio_np)
        if not text or len(text.strip()) < 2:
            self.ui.set_state("LISTENING")
            return
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
        if self._handle_greeting_reply(text):
            self.ui.set_state("LISTENING")
            return
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    # ── text path (from input box) ────────────────────────────────────
    def _on_text_command(self, text: str):
        self._last_interaction = time.time()
        if self._handle_greeting_reply(text):
            return
        # TASK 4 Fix: Handle interruption
        if self.ui.state in ("THINKING", "SPEAKING", "PROCESSING"):
            print("[JARVIS] ✋ Interrupted by text!")
            self.interrupt_event.set()
            _tts.stop()
            self.ui.write_log("Jarvis: [cancelled — interrupted]")
            
        self.ui.set_state("THINKING")
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    # ── core processing ───────────────────────────────────────────────
    def _process(self, user_text: str):
        """Send user_text to Ollama, handle tool calls, speak reply."""
        self.interrupt_event.clear()
        try:
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
                        print("[JARVIS] ✋ Stream interrupted!")
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

    # ── TTS output ────────────────────────────────────────────────────
    def _speak(self, text: str):
        # Task 13: Unconditional TTS with queue
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
        merged = "\n\n".join(parts)
        try:
            from agent.orchestrator import enrich_system_prompt
            merged = enrich_system_prompt(merged, user_text)
        except ImportError:
            pass
        return merged

    # ── tool executor ─────────────────────────────────────────────────
    def _execute_tool(self, name: str, args: dict) -> Any:
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
                return market_tracker(parameters=args, player=ui) or "Market data retrieved."

            elif name == "open_app":
                return open_app(parameters=args, response=None, player=ui) or f"Opened {args.get('app_name')}."

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