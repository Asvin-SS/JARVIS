# Mark-XXXIX User Manual

**Version:** Mark-XXXIX (3.9)  
**Author:** SS

This manual explains how to install, run, and use Mark-XXXIX day to day. For a quick overview see `README.md`. For verification steps see `TASK_CHECKLIST.md`.

---

## 1. Installation

### 1.1 Prerequisites

1. Install [Python 3.10+](https://www.python.org/downloads/) (check **Add to PATH** on Windows).
2. Install [Ollama](https://ollama.com/download).
3. Install [Git](https://git-scm.com/) if cloning the repo.
4. Microphone + speakers (optional if you only type commands).

### 1.2 Project setup

```powershell
cd C:\path\to\Mark-XXXIX-main
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
ollama pull mistral
```

Optional — local coding agent (uses Ollama or Aider CLI):

```powershell
pip install aider-chat
```

### 1.3 First run

```powershell
ollama serve
python main.py
```

- First launch: complete the **OS setup** overlay (Windows / macOS / Linux).
- The main window opens with the **dashboard**, **HUD**, and **activity log**.
- Jarvis speaks a short greeting (*Good morning/afternoon/evening, SS*).
- By default the window **stays visible** and the microphone is active.

---

## 2. Project folder structure

```
Mark-XXXIX-main/
├── main.py                 # Entry point — voice, TTS, LLM, tool routing
├── jarvis_ui.py            # PyQt6 main window, dashboard, tray, HUD
├── ui_settings.py          # Settings dialog (Models, Voice, Smart Home, Startup)
├── llm_client.py           # Ollama / OpenAI / Anthropic, tools, model catalog
├── smart_home.py           # Home Assistant integration
│
├── actions/                # One file per tool (Jarvis capabilities)
│   ├── browser_control.py
│   ├── coding_bridge.py    # Local code edit (Ollama + optional Aider)
│   ├── code_helper.py
│   ├── dev_agent.py        # Multi-file project builder
│   ├── market_tracker.py
│   ├── screen_processor.py
│   ├── weather_report.py
│   └── …
│
├── agent/                  # Unified agent layer
│   ├── orchestrator.py     # Intent hints in system prompt
│   ├── task_queue.py       # Background multi-step tasks
│   ├── planner.py
│   └── executor.py
│
├── core/                   # Config, identity, hardware, vision
│   ├── config.py           # Paths, timeouts, model roles
│   ├── identity.txt        # Jarvis persona (SS / Mark-XXXIX)
│   ├── prompt.txt          # Execution rules
│   ├── language.py         # Tanglish / Tamil / STT language
│   ├── hardware_profile.py # RAM/CPU scan → best Ollama model
│   ├── model_router.py     # Route coding / vision / reasoning models
│   └── vision_backend.py   # Screen vision (llava / fallback)
│
├── services/
│   └── weather_service.py  # Cached weather (wttr.in + open-meteo fallback)
│
├── db/
│   ├── database.py         # SQLite API
│   └── jarvis.db           # Auto-created (gitignored)
│
├── memory/                 # Long-term memory + session helpers
├── diagnostics/            # Startup health checks
├── ui/
│   ├── activity_panel.py   # Right-side “agent task” strip during tools
│   └── screen_overlay.py   # Mini screen preview during vision
│
├── tests/
│   └── system_validation.py
│
├── config/                 # settings.json, api_keys.json (gitignored)
├── docs/LOCAL_MODELS.md
├── logs/                   # jarvis.log (gitignored)
├── knowledge/optimizely/   # Enterprise commerce notes
├── capability_registry/
├── self_upgrade/
│
├── README.md
├── MANUAL.md               # This file
├── TASK_CHECKLIST.md
└── requirements.txt
```

**Runtime data:** `db/jarvis.db`, `config/settings.json`, `config/api_keys.json`, `logs/`.

---

## 3. Understanding the interface

### 3.1 Layout

```
┌──────────┬─────────────┬──────────────┬────────────┬─────────────────┐
│ Metrics  │  HUD face   │  Dashboard   │ Agent task │  Activity log   │
│ CPU/RAM  │  + status   │  Tasks       │  (tools)   │  + file upload  │
│          │             │  Watchlist   │            │  + command box  │
│          │             │  Smart home  │            │                 │
│          │             │  Weather     │            │                 │
└──────────┴─────────────┴──────────────┴────────────┴─────────────────┘
```

| Area | Location | Purpose |
|------|----------|---------|
| **System monitor** | Left strip | CPU, RAM, network, GPU, temperature, uptime |
| **HUD** | Center | Animated face / listening ring |
| **Dashboard** | Left of chat | Tasks, watchlist, smart home, weather |
| **Agent task** | Thin right strip | Live status while a tool runs (browser, code, etc.) |
| **Activity log** | Right | Conversation history |
| **Command input** | Bottom right | Type commands |
| **File upload** | Right panel | Drag & drop files for analysis |

### 3.2 Dashboard

If tasks or watchlist look empty:

1. **Widen the window** — minimum ~1100px recommended.
2. Click **`>`** between HUD and chat if the dashboard is collapsed.
3. Say or type **`refresh dashboard`**.

Auto-refresh intervals: tasks 30s · watchlist 5min · weather 30min · smart home 15s.

### 3.3 Header and shortcuts

| Control | Action |
|---------|--------|
| **⚙ SETTINGS** | Models, voice, smart home, startup |
| **F4** | Toggle **microphone mute** (TTS still works) |
| **F11** | Fullscreen |
| **Enter** | Send typed command |

### 3.4 System tray

| Menu | Action |
|------|--------|
| **Show** | Open window + start voice capture |
| **Hide** | Minimize to tray + wake word listener |
| **Quit** | Exit (session summary saved if Ollama is up) |

---

## 4. Voice and chat behaviour

### 4.1 Normal flow

1. Window visible → microphone listens (unless muted).
2. Speak or type a command.
3. Orange ring = **processing** (LLM / tools).
4. Jarvis **writes** the full reply in the log and **speaks** a short version (TTS enabled in Settings).

### 4.2 Stop — the only interrupt

Jarvis **does not** cancel on background noise or random speech.

To cancel the current reply or tool:

- Say or type: **`stop`**, **`Jarvis stop`**, **`okay Jarvis stop`**, **`cancel`**

While Jarvis is busy, new voice input is **ignored** until you say stop or the task finishes.

### 4.3 Fast commands (no Ollama required)

These work even when `ollama serve` is offline:

| Say or type | Result |
|-------------|--------|
| `list tasks` / `what are my pending tasks` | Reads tasks from SQLite |
| `pull weather` / `today's weather` | Cached weather line |
| `show watchlist` / `groww` | Watchlist symbols |
| `add task: …` | Saves task + refreshes dashboard |
| `add RELIANCE to watchlist` | Adds symbol |
| `refresh dashboard` | Refreshes all dashboard cards |
| Tamil language question | Short spoken answer (Tamil/Tanglish supported) |
| `open chrome and youtube` | Opens browser (fast path) |

### 4.4 Tamil and Tanglish

- **Settings → Voice → Reply language:** `tanglish` (default), `english`, or `tamil`.
- **Speech-to-text:** `auto`, `en`, or `ta` (Whisper **base** multilingual model).
- Example: *"Can you understand Tamil?"* → fast local answer without LLM.

### 4.5 Wake word (tray mode)

When the window is **hidden**:

1. Say **"Jarvis"** or **"Hey Jarvis"**.
2. Window opens, chime, *"I'm listening, SS."*
3. Speak your command.

Requires `SpeechRecognition` + `pyaudio` (see §15).

### 4.6 Idle mode (permission required)

After **90 seconds** with no interaction, Jarvis asks:

> *"SS, should I go idle and minimize? Say yes or no."*

- **Yes** → minimizes to tray (wake word stays active).
- **No** → stays on screen; timer resets.

Jarvis will **not** disappear without asking.

---

## 5. Settings

Open **⚙ SETTINGS** in the header.

### 5.1 Models tab

- Pick an **installed** Ollama model (from `ollama list`).
- **Warm up selected model** — loads weights into RAM.
- **Install open-source models** — pull from catalog.
- **API keys** — OpenAI / Anthropic (optional cloud fallback).

### 5.2 Voice tab

| Option | Purpose |
|--------|---------|
| Enable speech (TTS) | Speak replies aloud |
| Require "Jarvis" prefix | Ignore voice that doesn't start with Jarvis |
| Reply language | tanglish / english / tamil |
| Speech-to-text | auto / en / ta |
| Wake word sensitivity | Low / Medium / High |

Mic mute (F4) stops **listening only** — chat log and TTS are separate.

### 5.3 Smart Home tab

Home Assistant URL + long-lived token. **Test connection** then **Save**.

### 5.4 Startup tab

| Option | Default | Purpose |
|--------|---------|---------|
| Start minimised to tray | Off | Window visible on launch |
| Run greeting sequence | On | Spoken time/date greeting |
| Show active tasks on startup | On | Mention task count in greeting |
| Default weather city | Chennai | Dashboard + weather tools |

### 5.5 Hardware-adaptive model

On startup, Mark-XXXIX scans RAM/CPU and picks the best local model (`core/hardware_profile.py`).

Controlled in `config/settings.json`:

```json
"auto_hardware_model": true,
"auto_pull_model": true
```

If Ollama is offline, hardware scan is saved but model switch waits until `ollama serve` runs.

---

## 6. Tasks and memory

### Creating tasks

- Voice: *"Remind me to finish the report tomorrow."*
- Fast: **`add task: call client at 3pm`**
- LLM tool: `save_task` when Jarvis detects a goal

Tasks appear in **📋 Active Tasks** and in `db/jarvis.db`. Test rows (`category: test`) are hidden from the dashboard.

### Catch-up

- *"What was I doing?"*
- *"Catch me up."*

Uses last session summary + recent conversation rows.

---

## 7. Stock watchlist

| Command | Result |
|---------|--------|
| Add RELIANCE.NS to my watchlist | Saves symbol |
| Show my watchlist | Dashboard + spoken list |
| Open Groww | Browser → Groww |
| What is TCS.NS trading at? | Price via `market_tracker` |

Indian NSE symbols often need the **`.NS`** suffix.

---

## 8. Smart home

1. Configure Home Assistant in **Settings → Smart Home**.
2. Dashboard **🏠** shows devices when connected.
3. Examples: *"Turn on the living room light."*

---

## 9. Screen and vision

| Mode | Trigger | UI |
|------|---------|-----|
| On-demand | "View my screen" | Mini **screen overlay** (top-left) |
| Continuous | "Keep watching my screen" | Overlay updates every ~30s |
| Stop | "Stop watching" | Overlay closes |

Uses local **llava** when installed; optional cloud vision fallback in settings.

---

## 10. Coding and debugging

| Tool | Use |
|------|-----|
| `code_helper` | Write, explain, run snippets |
| `coding_bridge` | Edit/fix a file locally (Ollama; **Aider** if installed) |
| `dev_agent` | Build multi-file projects from description |

Install Aider for stronger repo-aware edits:

```powershell
pip install aider-chat
```

During tool runs, watch the **Agent task** strip on the right for live status.

---

## 11. Files

1. Drag a file onto **FILE UPLOAD**.
2. Ask: *"Summarize this PDF"* or *"Extract tables from this spreadsheet."*

Supported: PDF, Office, images, code, archives (see `actions/file_processor.py`).

---

## 12. Building new tools

Ask: *"Build me a tool that tracks my daily water intake."*

Jarvis uses `dev_agent.py` to write `actions/your_tool.py`, register it, and confirm in chat + voice.

---

## 13. Shutting down

- Tray → **Quit**, or
- *"Goodbye Jarvis"* / shutdown command.

Session summary is saved to the database when Ollama is available.

---

## 14. Data and privacy

| Data | Location |
|------|----------|
| Conversations, tasks, sessions | `db/jarvis.db` |
| API keys | `config/api_keys.json` (gitignored) |
| Settings | `config/settings.json` |
| Logs | `logs/jarvis.log` |

Back up `db/` and `config/` before reinstalling Windows.

---

## 15. Common problems

### Ollama connection error

```powershell
ollama serve
curl http://localhost:11434/api/tags
```

Fast commands (tasks, weather, Tamil FAQ) still work without Ollama.

### No speech (TTS silent)

1. **Settings → Voice** → enable **Enable speech (TTS on every reply)**.
2. Check Windows volume / default output device.
3. Terminal should not show repeated `(no TTS)` lines.

### Constant “Stopped” or no response

- You may have said **stop** — send a fresh command.
- Wait until the orange **processing** state clears before sending another.

### Dashboard empty

- Create a task: `add task: test item`
- `refresh dashboard`
- Widen window; expand with **`>`**

### Weather stuck on “Loading…”

- Check internet; service tries wttr.in then open-meteo.
- Set city in **Settings → Startup → Default weather city**.

### Mic / wake word errors (Windows)

```powershell
pip install pyaudio faster-whisper sounddevice SpeechRecognition
```

### PyAudio pip failure

Install a prebuilt wheel matching your Python version.

### Hugging Face Whisper warning

Harmless on Windows. Optional: set `HF_HUB_DISABLE_SYMLINKS_WARNING=1` or enable Windows Developer Mode for symlinks.

### Slow local model

```powershell
$env:OLLAMA_TIMEOUT_SEC = "900"
python main.py
```

Warm up model in **Settings → Models**.

---

## 16. Developer quick reference

| Task | Command / file |
|------|----------------|
| Run tests | `python -m tests.system_validation` |
| Health check | `diagnostics/system_diagnostics.py` |
| Change persona | `core/identity.txt` |
| Change timeouts | `core/config.py` or env `OLLAMA_TIMEOUT_SEC` |
| Add a tool | New file in `actions/` + register in `main.py` `TOOL_DECLARATIONS` |

---

## 17. Keyboard shortcuts

| Key | Action |
|-----|--------|
| F4 | Toggle microphone mute |
| F11 | Fullscreen |
| Enter | Send typed command (when input focused) |

---

*Mark-XXXIX — A product of SS*
