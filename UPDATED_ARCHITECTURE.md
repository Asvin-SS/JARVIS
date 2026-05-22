# Mark-XXXIX — Updated Architecture (summary)

## Layers

```
PyQt6 UI (ui.py, ui_settings.py)
    ↕ signals
JarvisLocal (main.py) — voice, TTS queue, wake word, greeting
    ↕
llm_client.py — Ollama/OpenAI, tool filter, retry, model router
    ↕
actions/* — tools (market, files, screen, dev_agent, …)
    ↕
db/database.py — SQLite persistence
```

## New packages

| Path | Role |
|------|------|
| `core/` | Config, logging, identity, model routing |
| `services/` | Background services (weather cache) |
| `diagnostics/` | Pass/fail health report |
| `agent/orchestrator.py` | Planner injection (Phase 7 seed) |
| `knowledge/optimizely/` | Enterprise commerce docs |
| `capability_registry/` | What exists vs missing |
| `self_upgrade/` | Future adaptive modules |
| `logs/`, `backups/`, `snapshots/` | Runtime (gitignored) |

## Threading rules

- UI thread: Qt only
- `JarvisLocal._process`: worker thread
- TTS: dedicated queue thread
- Dashboard refresh: background threads → `QTimer.singleShot` to UI
- Ollama: blocking HTTP in worker (never on UI thread)

## Modes (planned)

- **SAFE** — suggestions only (default behavior with approval gates)
- **ASSISTED** — file edits after confirm
- **AUTONOMOUS** — not fully enabled; requires explicit future flag

See `CHANGELOG.md` for incremental changes.
