"""Automated integration checks (run: python -m tests.system_validation)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_db_init():
    from db.database import init_db, save_task, get_active_tasks, DB_PATH
    init_db()
    assert DB_PATH.exists()
    save_task("validation-test", "auto test", "test")
    tasks = get_active_tasks()
    assert any("validation-test" in t["title"] for t in tasks)


def test_weather_cache():
    from services.weather_service import fetch_weather
    w = fetch_weather("Chennai")
    assert "raw_line" in w


def test_tool_filter():
    from llm_client import get_relevant_tools, CORE_TOOL_NAMES
    tools = [{"name": n} for n in list(CORE_TOOL_NAMES) + ["dev_agent", "game_updater"]]
    out = get_relevant_tools("hello there", tools)
    assert len(out) <= 12
    assert all(t["name"] in CORE_TOOL_NAMES for t in out)


def main():
    tests = [test_db_init, test_weather_cache, test_tool_filter]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
