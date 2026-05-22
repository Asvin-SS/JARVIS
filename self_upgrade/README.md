# Self-upgrade modules

When Jarvis lacks a capability it must not fake it. Flow:

1. Detect gap (see `capability_registry/registry.json`)
2. Explain to SS
3. Generate module under `generated_tools/` or `actions/`
4. Register via `importlib` in `main.py`
5. Record in `self_built_tools` table

Autonomous installs require explicit approval (ASSISTED/AUTONOMOUS mode).
