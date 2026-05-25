# Mark-XXXIX — Developer Guide

Quick orientation for SS and contributors.

## Entry points

| File | Role |
|------|------|
| `main.py` | Voice, TTS queue, LLM `_process`, tool executor |
| `jarvis_ui.py` | PyQt6 window, dashboard, tray |
| `ui_settings.py` | Settings tabs |
| `llm_client.py` | Ollama / OpenAI / Anthropic + tool filter |

## Add a new tool

1. Create `actions/my_tool.py` with a `run(parameters, player, speak)` function.
2. Add a `TOOL_DECLARATIONS` entry in `main.py`.
3. Add an `elif name == "my_tool"` branch in `_execute_tool_inner`.
4. Optional: add keyword mapping in `llm_client.get_relevant_tools()`.

## UI widgets

| Module | Purpose |
|--------|---------|
| `ui/mini_hud.py` | Floating HUD when main window hidden |
| `ui/activity_panel.py` | Tool execution strip |
| `ui/screen_overlay.py` | Vision preview |

## Agents

| Module | Purpose |
|--------|---------|
| `actions/coding_agent.py` | Screen + Aider/Ollama debug |
| `actions/optimizely_agent.py` | OCC knowledge + Claude |
| `actions/trading_agent.py` | Daily market briefing |
| `self_upgrade/upgrade_manager.py` | Git-branch self upgrades |

## Tests

```powershell
python -m tests.system_validation
```

## Run

```powershell
ollama serve
python main.py
```

See `MANUAL.md` for user-facing documentation.
