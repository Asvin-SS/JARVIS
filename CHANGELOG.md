# Changelog

## Unreleased — Engineering assistant foundation

### Added
- `core/config.py` — 3600s timeouts, runtime directories
- `core/logging_setup.py` — `logs/jarvis.log`
- `core/model_router.py` — coding / vision / reasoning model selection
- `services/weather_service.py` — cached wttr.in weather for dashboard
- `agent/orchestrator.py` — multi-agent plan injection
- `diagnostics/system_diagnostics.py` — startup health checks
- `tests/system_validation.py` — DB, weather, tool-filter tests
- `knowledge/optimizely/` — commerce knowledge placeholder
- `capability_registry/registry.json` — honest capability map

### Fixed
- Ollama: default timeout **3600s**, retry + backoff, core-tool-only when intent unknown
- TTS: **mic mute no longer disables speech**; `speech_enabled` in Settings
- Voice: **Jarvis prefix** filter reduces false triggers
- Tasks: `db.save_task()` helper + dashboard refresh
- Weather: reliable cached API path for dashboard

### Changed
- `llm_client.py` — `_ollama_chat_with_retry`, `MAX_TOOLS_PER_REQUEST`
