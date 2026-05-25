# Changelog

## Unreleased — Mark-XXXIX unified agent

### Added
- `jarvis_ui.py` — main PyQt6 UI (replaces legacy `ui.py`)
- `ui_settings.py` — tabbed settings (models, voice, smart home, startup)
- `ui/activity_panel.py` — agent task strip during tool execution
- `ui/screen_overlay.py` — mini screen preview for vision mode
- `core/hardware_profile.py` — RAM/CPU scan → auto Ollama model pick
- `actions/coding_bridge.py` — local code edit (Ollama + optional Aider)
- `services/weather_service.py` — wttr.in + open-meteo fallback
- Stop-only interrupt policy; idle minimize asks yes/no first
- Fast commands: tasks, weather, watchlist, Tamil FAQ, Chrome/YouTube (no LLM)
- Multilingual Whisper (`base`) for Tamil STT

### Fixed
- Greeting wizard no longer hijacks normal questions (`run_greeting_steps` off by default)
- TTS blocks until speech finishes; mic echo guard
- Dashboard dedupes tasks; test rows hidden from active list
- Session summary skips LLM when Ollama offline
- Single mic stream (no double `start()`)

### Removed
- `ui.py` → use `jarvis_ui.py`
- `ui_model_manager.py` → use `ui_settings.py`
- `core/model_backend.py` (unused shim)
- `UPDATED_ARCHITECTURE.md` (merged into MANUAL.md)
- Duplicate `readme.md`

### Changed
- `MANUAL.md` — full folder structure and current behaviour
- Default window visible on launch (`start_minimized: false`)
