"""Daily trading briefing — watchlist + news + recommendations."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

_LAST_BRIEFING_FILE = Path(__file__).resolve().parent.parent / "db" / "last_briefing.json"


def _already_briefed_today() -> bool:
    try:
        data = json.loads(_LAST_BRIEFING_FILE.read_text(encoding="utf-8"))
        return data.get("date") == str(date.today())
    except Exception:
        return False


def _mark_briefed():
    _LAST_BRIEFING_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_BRIEFING_FILE.write_text(json.dumps({"date": str(date.today())}), encoding="utf-8")


def trading_briefing(parameters: dict | None = None, player=None, speak=None) -> str:
    p = parameters or {}
    force = p.get("force", False)
    if _already_briefed_today() and not force:
        return "Trading briefing already delivered today. Say 'force trading briefing' to refresh."

    results = []

    try:
        from db.database import get_watchlist
        from actions.market_tracker import run as market_tracker
        watch = get_watchlist()
        if watch:
            for w in watch[:6]:
                try:
                    r = market_tracker({"action": "get_price", "symbol": w["symbol"]})
                    results.append(str(r))
                except Exception:
                    results.append(w["symbol"])
    except Exception as e:
        results.append(f"Prices unavailable: {e}")

    try:
        from actions.web_search import web_search as web_search_action
        news = web_search_action({"query": "India stock market NSE BSE news today"})
        results.append(f"Market news: {str(news)[:600]}")
    except Exception as e:
        results.append(f"News unavailable: {e}")

    combined = "\n".join(results)
    try:
        from llm_client import unified_chat, is_ollama_running
        if is_ollama_running():
            prompt = f"""Based on this market data for today ({datetime.now().strftime('%A %d %B %Y')}):

{combined}

Give SS (retail trader, India NSE/BSE) 3 short recommendations.
Format: symbol → action → reason (1 line each). Educational only, not financial advice."""
            rec = unified_chat("You are a market analyst.", prompt)
            results.append(f"\nRecommendations:\n{rec}")
    except Exception as e:
        results.append(f"Analysis failed: {e}")

    _mark_briefed()
    final = "\n".join(results)

    if player:
        player.write_log(f"Jarvis (Trading): {final[:800]}")
    if speak and results:
        speak(f"Good morning SS. Market briefing ready. {results[0][:180]}")

    return final


def is_first_wake_today() -> bool:
    return not _already_briefed_today()
