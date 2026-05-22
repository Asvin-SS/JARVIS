# Mark-XXXIX User Manual

**Version:** Mark-3.9  
**Author:** SS

This manual explains how to install, run, and use Mark-XXXIX day to day. For developers, see `README.md` and `TASK_CHECKLIST.md`.

---

## 1. Installation

### 1.1 Prerequisites

1. Install [Python 3.10+](https://www.python.org/downloads/) (check **Add to PATH** on Windows).
2. Install [Ollama](https://ollama.com/download).
3. Install [Git](https://git-scm.com/) if cloning the repo.

### 1.2 Project setup

```powershell
cd C:\path\to\Mark-XXXIX-main
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
ollama pull mistral
```

### 1.3 First run

```powershell
ollama serve
python main.py
```

- A window opens with a short **OS selection** overlay (first time only).
- After setup, Jarvis greets you (**Good morning/afternoon/evening, SS**), then the window moves to the **system tray**.

---

## 2. Understanding the interface

### 2.1 Layout

| Area | Location | Purpose |
|------|----------|---------|
| **System monitor** | Left strip | CPU, RAM, network, GPU, temperature |
| **HUD** | Center | Animated face / status ring |
| **Dashboard** | Between HUD and chat | Tasks, watchlist, smart home, weather |
| **Activity log** | Right | Conversation history |
| **Command input** | Bottom right | Type commands |
| **File upload** | Right panel | Drag & drop files for analysis |

### 2.2 Dashboard (important)

If you do not see tasks or watchlist:

1. **Widen the window** — minimum width ~1100px recommended.
2. Look for the **`>`** button between the HUD and the chat panel — click it to **expand** the dashboard.
3. Sections refresh automatically:
   - Tasks: every 30 seconds  
   - Watchlist: every 60 seconds  
   - Weather: every 30 minutes  
   - Smart home: every 15 seconds  

### 2.3 Header controls

- **⚙ MODELS** — Change LLM, API keys, warm up model.
- **Clock** — Local time and date.
- **F4** — Toggle microphone mute (TTS can still run unless you use mute for voice-only; see §5).
- **F11** — Fullscreen.

### 2.4 System tray

- **Show** — Open the main window (starts voice capture).
- **Hide** — Minimize to tray (wake word active).
- **Quit** — Exit the application.

---

## 3. Voice usage

### 3.1 Tray + wake word flow

1. App starts in tray after greeting.
2. Say **"Jarvis"** or **"Hey Jarvis"** (clearly, near the mic).
3. Window opens; you hear a chime and *"I'm listening, sir."*
4. Speak your command in one sentence.
5. Jarvis thinks (orange ring), then speaks and logs the reply.

### 3.2 While the window is open

- The microphone is active when the window is **visible**.
- **Mute** with the mic button or **F4** — stops listening; use for privacy.
- **Interrupt**: speak or type a new command while Jarvis is answering — previous reply shows `[cancelled]`.

### 3.3 Typed commands

- Same brain as voice — type in **COMMAND INPUT** and press Enter or **▸**.
- Responses are **always shown** in the log and **spoken** unless TTS is blocked by an error.

---

## 4. Settings and models

### 4.1 Open settings

Click **⚙ MODELS** in the header.

### 4.2 Ollama models

- Only **installed** models appear (from `ollama list`).
- Select a radio button → saved immediately to `config/settings.json`.
- **WARM UP SELECTED MODEL** — loads weights into RAM (recommended after switching).

### 4.3 Cloud API keys

- **OpenAI** / **Anthropic** — paste keys, **Test**, then **SAVE & APPLY**.
- When a cloud provider is selected, Ollama is not used for that session's provider choice.

### 4.4 Timeouts

If local models are slow:

```powershell
$env:OLLAMA_TIMEOUT_SEC = "900"
python main.py
```

---

## 5. Mute and TTS

| Control | Effect |
|---------|--------|
| **🔇 MICROPHONE MUTED** | Stops voice *input*; preference saved in DB |
| Assistant replies | Still queued for TTS unless engine fails |
| Chat log | Always updated |

For silent operation, use typed commands only and lower system volume, or extend mute behavior in settings.

---

## 6. Tasks and memory

### 6.1 Creating tasks

Say or type:

- *"Remind me to finish the report tomorrow."*
- *"Track my habit: drink water daily."*
- *"I need to call the client at 3."*

Tasks appear in the dashboard **📋 Active Tasks** and in `db/jarvis.db`.

### 6.2 Startup recap

After the greeting, Jarvis may ask: *"Want me to recap your pending tasks?"*  
Answer **yes** or **no**.

### 6.3 Catch-up

- *"What was I doing?"*
- *"Catch me up."*

Uses the last session summary and recent conversation rows.

---

## 7. Stock watchlist

| Command | Result |
|---------|--------|
| Add RELIANCE.NS to my watchlist | Saves symbol |
| Show my watchlist | Lists symbols + prices |
| What is TCS.NS trading at? | Price quote |
| Open Groww | Opens Groww in browser |

Indian symbols often need `.NS` suffix (NSE).

---

## 8. Smart home

1. Configure Home Assistant URL and token (see `README.md`).
2. Dashboard **🏠** shows device names when connected.
3. Examples:
   - *"Turn on the living room light."*
   - *"Turn off bedroom switch."*

Jarvis parses intent and calls Home Assistant services.

---

## 9. Screen assistance

| Mode | Trigger | Behavior |
|------|---------|----------|
| **On-demand** | "View my screen" | One screenshot → vision analysis |
| **Continuous** | "Keep watching my screen" | Every 30s if screen changes |
| **Stop** | "Stop watching" | Ends monitoring |

Vision may temporarily use `llava` if the active text model has no vision support.

---

## 10. Files

1. Drag a file onto the **FILE UPLOAD** zone.
2. Jarvis acknowledges the file in chat.
3. Ask: *"Summarize this PDF"* or *"Extract tables from this spreadsheet."*

Supported types include PDF, Office docs, images, code, archives (see `file_processor.py`).

---

## 11. Building new tools

Ask:

> *"Build me a tool that tracks my daily water intake."*

Jarvis uses `dev_agent.py` to:

1. Ask one clarifying question.
2. Write `actions/your_tool.py`.
3. Register it live.
4. Confirm in voice and chat.

---

## 12. Shutting down

- Tray → **Quit**, or
- *"Goodbye Jarvis"* / shutdown command if implemented in your build.

On close, a **session summary** is written to the database.

---

## 13. Data and privacy

| Data | Location |
|------|----------|
| Conversations, tasks, sessions | `db/jarvis.db` |
| API keys | `config/api_keys.json` (gitignored) |
| Settings | `config/settings.json` |

Back up `db/` and `config/` if you reinstall Windows.

---

## 14. Common problems

### Dashboard empty

- No tasks in DB yet — create one via voice.
- Watchlist empty — add a symbol first.
- Weather fails — check internet / `weather_report` dependencies.

### Ollama connection error

```powershell
ollama serve
curl http://localhost:11434/api/tags
```

### App closes immediately

Run from terminal to see errors:

```powershell
python main.py
```

### PyAudio / mic errors (Windows)

```powershell
pip install pyaudio
```

If pip fails, install a prebuilt wheel for your Python version.

---

## 15. Keyboard shortcuts

| Key | Action |
|-----|--------|
| F4 | Toggle microphone mute |
| F11 | Fullscreen |
| Enter | Send typed command (when input focused) |

---

## 16. Getting help

1. Read `README.md` troubleshooting table.
2. Walk through `TASK_CHECKLIST.md` and note which items fail.
3. Check the terminal for `[JARVIS]` and `[DB]` log lines.

---

*Mark-3.9 — A product of SS*
