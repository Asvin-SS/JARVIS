# Mark-XXXIX
Personal AI Agent — Built by SS

## What is this
Mark-XXXIX is a fully local, always-on personal AI desktop agent built in Python with a native PyQt6 UI. It listens for voice commands, executes actions via modular tools, and responds via voice and chat. Designed with privacy in mind, it runs entirely on your machine, acting as a "Jarvis-style" assistant for your desktop.

## Requirements
- **OS**: Windows (optimized for Windows 10/11)
- **Python**: 3.10+
- **AI Backend**: [Ollama](https://ollama.com/) (running locally)
- **Optional**: Home Assistant (for smart home control)

## First-time setup
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Asvinss/Jarvis-agent.git
    cd Jarvis-agent
    ```
2.  **Create a virtual environment**:
    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Install Ollama**: Download and install from [ollama.com](https://ollama.com/). Pull your preferred model (e.g., `ollama pull mistral:latest`).

## How to run
Simply run the main script:
```bash
python main.py
```
The app will start minimized in your system tray.

## Wake word
Mark-XXXIX uses background listening for the wake word.
- **Trigger**: Say "Jarvis", "Hey Jarvis", or "Wake up Jarvis".
- **Action**: The UI will restore from the tray, play a chime, and Jarvis will say "I'm listening, sir."
- **Auto-Minimize**: If idle for 60 seconds, the app will minimize back to the tray.

## Voice commands (examples)
- "Jarvis, what's the weather like in Chennai?"
- "Add RELIANCE.NS to my watchlist."
- "Show my watchlist."
- "What was I doing earlier?" (Catch-up feature)
- "Remind me to buy milk at 6 PM."
- "Open Chrome and search for local news."
- "Turn off the living room light." (Requires Smart Home setup)
- "Watch my screen." (Continuous monitoring)
- "Create a tool to track my habits." (Self-building capability)
- "What is AAPL trading at?"

## Models
You can switch models live via the **⚙ MODELS** button in the header.
- **Mistral**: Balanced, great for general tasks.
- **Llama 3.2**: Powerful and fast.
- **Llava**: Vision-capable (used for screen analysis).
Use the "Warm up" button in settings to preload your selected model into memory.

## Smart Home setup
1.  Open the Smart Home section in the side panel or settings.
2.  Enter your **Home Assistant URL** (e.g., `http://homeassistant.local:8123`).
3.  Paste your **Long-Lived Access Token** (generated in Home Assistant profile settings).
4.  Click "Save & Connect".

## Actions reference
| Action File | Description | Example Command |
| :--- | :--- | :--- |
| `browser_control.py` | Controls web browsers | "Open YouTube" |
| `market_tracker.py` | Tracks stocks & watchlist | "Show my watchlist" |
| `weather_report.py` | Real-time weather data | "How is the weather?" |
| `screen_processor.py` | Vision-based screen analysis | "View my screen" |
| `dev_agent.py` | Builds new tools for Jarvis | "Build a habit tracker" |
| `file_controller.py` | Manages local files | "Find my project folder" |
| `open_app.py` | Launches desktop applications | "Open Notepad" |

## Troubleshooting
- **Ollama timeout**: If models are slow, increase `OLLAMA_TIMEOUT_SEC` in your environment variables (default 600s).
- **Sounddevice error**: Ensure `pyaudio` and `sounddevice` are correctly installed. On Windows, you may need the [C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
- **Voice not working**: Check your default microphone in Windows settings and ensure it's not muted in the Jarvis UI.

## Project structure
```text
Mark-XXXIX/
├── actions/         # Modular tool implementation
├── agent/           # Orchestration and planning
├── config/          # User settings and API keys
├── core/            # Model backend and prompts
├── db/              # SQLite database (auto-created)
├── memory/          # Long-term memory and persistence
├── main.py          # Application entry point
├── ui.py            # PyQt6 UI implementation
└── requirements.txt # Project dependencies
```
---
**Mark-3.9 — A product of SS**
