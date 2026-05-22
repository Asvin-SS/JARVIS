"""Cached weather via wttr.in (no API key). Used by dashboard + greeting."""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from db.database import get_preference, set_preference

_CACHE_KEY = "weather_cache"
_CACHE_TTL = 30 * 60  # 30 minutes


def fetch_weather(city: str = "Chennai") -> dict[str, Any]:
    """
    Returns {city, temp_c, humidity, conditions, refreshed_at, raw_line}.
    Uses SQLite preferences cache.
    """
    city = (city or "Chennai").strip()
    cached = _load_cache()
    if cached and cached.get("city", "").lower() == city.lower():
        if time.time() - cached.get("_ts", 0) < _CACHE_TTL:
            return cached

    try:
        url = f"https://wttr.in/{requests.utils.quote(city)}?format=j1"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mark-XXXIX/1.0"})
        r.raise_for_status()
        data = r.json()
        cur = (data.get("current_condition") or [{}])[0]
        temp = cur.get("temp_C", "?")
        hum = cur.get("humidity", "?")
        desc = ((cur.get("weatherDesc") or [{}])[0]).get("value", "Unknown")
        out = {
            "city": city,
            "temp_c": temp,
            "humidity": hum,
            "conditions": desc,
            "refreshed_at": time.strftime("%H:%M"),
            "raw_line": f"{city} · {temp}°C · {desc} · Humidity {hum}%",
            "_ts": time.time(),
        }
        set_preference(_CACHE_KEY, json.dumps(out))
        return out
    except Exception as e:
        return {
            "city": city,
            "temp_c": "?",
            "humidity": "?",
            "conditions": "unavailable",
            "refreshed_at": "",
            "raw_line": f"Weather unavailable ({e})",
            "_ts": time.time(),
        }


def format_weather_line(city: str = "Chennai") -> str:
    w = fetch_weather(city)
    ref = w.get("refreshed_at", "")
    suffix = f" (updated {ref})" if ref else ""
    return w.get("raw_line", "Weather unavailable.") + suffix


def _load_cache() -> dict[str, Any] | None:
    raw = get_preference(_CACHE_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
