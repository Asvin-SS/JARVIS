# Mark-XXXIX — Implementation Verification Checklist

Use this list to verify each item after setup. Check boxes as you confirm behavior.

---

## Critical bugs

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| BUG 1a | Ollama timeout default 600s (`OLLAMA_TIMEOUT_SEC`) | Voice command on slow model completes or fails after 600s, not 120s | ☐ |
| BUG 1b | Streaming into chat | Type a question; text appears word-by-word in Activity Log | ☐ |
| BUG 1c | Intent-based tool subset | Say "what's the weather" — faster than sending all tools | ☐ |
| BUG 1d | Model warm-up on startup | Console shows `[JARVIS] Warming up …` then `Model … ready` | ☐ |
| BUG 2 | Model switch without restart | ⚙ MODELS → pick another model → ask "what model are you" | ☐ |
| BUG 3 | TTS on every assistant reply | Voice + typed commands both speak (unless muted) | ☐ |
| BUG 3b | TTS fallback | If primary TTS fails, pyttsx3 still speaks (check console) | ☐ |
| BUG 4 | `google.genai` in file_processor | No deprecation warning on import/run | ☐ |
| BUG 5 | `sounddevice` in requirements | Fresh venv: `pip install -r requirements.txt` then `python main.py` starts | ☐ |

---

## Database (Task 1)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 1.1 | `db/jarvis.db` auto-created | Delete `db/jarvis.db`, run app — file recreated | ☐ |
| 1.2 | Tables exist | conversations, tasks, watchlist, preferences, sessions | ☐ |
| 1.3 | `init_db()` before UI | No crash on first run | ☐ |

---

## Wake word (Task 2)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 2.1 | Starts minimized to tray | After greeting, window hides; tray icon visible | ☐ |
| 2.2 | "Jarvis" / wake phrase restores window | Say wake phrase; window + chime + "I'm listening" | ☐ |
| 2.3 | Idle 60s → tray | Leave window open 60s idle → minimizes | ☐ |
| 2.4 | Wake sensitivity in settings | ⚙ MODELS or settings (if exposed) | ☐ |

---

## Startup greeting (Task 3)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 3.1 | Time-based greeting for SS | Hear "Good morning/afternoon/evening, SS" | ☐ |
| 3.2 | Weather in greeting | Weather line in speech + log | ☐ |
| 3.3 | Active tasks mentioned | Create task in DB; restart — mentioned in greeting | ☐ |
| 3.4 | Session row in `sessions` | New row after startup | ☐ |
| 3.5 | Dashboard shows tasks | **Dashboard panel** (between HUD and chat) lists tasks | ☐ |

---

## Interruption (Task 4)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 4.1 | Voice interrupts LLM | Speak while Jarvis is thinking/speaking → `[cancelled]` | ☐ |
| 4.2 | Typed interrupt | Send new message while processing → cancels prior | ☐ |

---

## Self-building tools (Task 5)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 5.1 | dev_agent extends | "Build a habit tracker tool" → clarifies → creates `actions/` file | ☐ |
| 5.2 | Live registration | New tool works without restart | ☐ |
| 5.3 | DB task `self_built_tool` | Row in `tasks` table | ☐ |

---

## Screen view (Task 6)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 6.1 | On-demand screen | "View my screen" → analysis in chat + TTS | ☐ |
| 6.2 | Continuous watch | "Keep watching my screen" / "stop watching" | ☐ |

---

## Market tracker (Task 7)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 7.1 | Add to watchlist | "Add RELIANCE.NS to watchlist" | ☐ |
| 7.2 | Dashboard watchlist | Prices/lines in 📈 section | ☐ |
| 7.3 | Open Groww/Zerodha | Browser opens broker URL | ☐ |

---

## UI dashboard (Task 8) — **your missing piece**

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 8.1 | Dashboard visible | Panel between HUD and Activity Log (~280px) | ☐ |
| 8.2 | Collapse toggle | `<` / `>` button hides/shows dashboard | ☐ |
| 8.3 | Sections | JARVIS status, Tasks, Watchlist, Smart Home, Weather | ☐ |
| 8.4 | Auto-refresh | Tasks ~30s, watchlist ~60s, weather ~30min, HA ~15s | ☐ |

---

## Smart home UI (Task 9)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 9.1 | HA URL/token in settings | Configure in settings / smart_home | ☐ |
| 9.2 | Device list in dashboard | 🏠 section shows devices when connected | ☐ |
| 9.3 | Voice "turn off bedroom light" | Works via smart_home + LLM | ☐ |

---

## Model settings (Task 10)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 10.1 | Radio list + descriptions | ⚙ MODELS shows installed Ollama models | ☐ |
| 10.2 | Tags fast/balanced/etc. | Badge per model | ☐ |
| 10.3 | Warm up button | "WARM UP SELECTED MODEL" → ready message | ☐ |
| 10.4 | OpenAI/Anthropic keys + Test | Save and test buttons | ☐ |
| 10.5 | No Gemini in UI | No Google API fields | ☐ |

---

## Branding (Task 11)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 11.1 | Window title `Mark-3.9` | Title bar | ☐ |
| 11.2 | No FaithMakes/FatihMakes footer | Bottom is chat input only (no company footer) | ☐ |
| 11.3 | Header shows Mark-3.9 | Top-left badge | ☐ |

---

## Task persistence (Task 12)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 12.1 | Auto-save tasks from conversation | `save_task` tool / memory_manager | ☐ |
| 12.2 | Recap prompt on startup | Greeting asks about pending tasks | ☐ |
| 12.3 | "Catch me up" | Reads last session + conversations | ☐ |
| 12.4 | Session summary on close | Close window → `sessions.summary` filled | ☐ |

---

## Voice reliability (Task 13)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 13.1 | TTS queue thread | Responses don't freeze UI | ☐ |
| 13.2 | Mute skips TTS only | 🔇 mute — chat still works, no speech | ☐ |
| 13.3 | Mute in DB | `preferences` key `muted` | ☐ |

---

## Documentation (Task 14)

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| 14.1 | README.md complete | Sections per spec | ☐ |
| 14.2 | MANUAL.md | User guide present | ☐ |

---

## Git / repo hygiene

| # | Item | How to verify | Status |
|---|------|---------------|--------|
| G.1 | `.gitignore` excludes venv, db, secrets | `git status` clean of `.venv`, `jarvis.db`, `api_keys.json` | ☐ |

---

## Quick run test (end-to-end)

1. `python -m venv .venv` → activate → `pip install -r requirements.txt`
2. `ollama serve` + `ollama pull mistral`
3. `python main.py`
4. Complete OS setup overlay if shown
5. Confirm **dashboard** with tasks section
6. Say wake word or show from tray
7. Ask: "What's the weather?"

---

*Last updated: implementation pass for dashboard + UI/main integration.*
