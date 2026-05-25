"""Cached weather — wttr.in with open-meteo fallback."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests as _req

_CACHE_FILE = Path(__file__).resolve().parent.parent / "db" / "weather_cache.json"
_CACHE_TTL = 1800  # 30 min


def _load_cache(city: str) -> str | None:
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if data.get("city", "").lower() == city.lower() and time.time() - data.get("ts", 0) < _CACHE_TTL:
            return data.get("line")
    except Exception:
        pass
    return None


def _save_cache(city: str, line: str) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"city": city, "line": line, "ts": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _wmo_desc(code: int) -> str:
    mapping = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 61: "Light rain",
        63: "Moderate rain", 65: "Heavy rain", 71: "Light snow", 80: "Rain showers",
        95: "Thunderstorm", 99: "Heavy thunderstorm",
    }
    return mapping.get(code, f"Code {code}")


def format_weather_line(city: str = "Chennai") -> str:
    city = (city or "Chennai").strip()
    cached = _load_cache(city)
    if cached:
        return cached

    try:
        r = _req.get(
            f"https://wttr.in/{quote(city)}?format=j1",
            timeout=8,
            headers={"User-Agent": "JarvisWeather/1.0"},
        )
        if r.status_code == 200:
            d = r.json()
            cur = d["current_condition"][0]
            temp_c = cur["temp_C"]
            feels = cur.get("FeelsLikeC", temp_c)
            desc = cur["weatherDesc"][0]["value"]
            humid = cur["humidity"]
            line = f"{city}: {temp_c}°C (feels {feels}°C), {desc}, humidity {humid}%"
            _save_cache(city, line)
            return line
    except Exception as e:
        print(f"[Weather] wttr.in failed: {e}")

    try:
        geo = _req.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=6,
        ).json()
        results = geo.get("results") or []
        if not results:
            return f"{city}: Weather unavailable right now."
        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        label = loc.get("name", city)

        wx = _req.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": True},
            timeout=8,
        ).json()
        cw = wx["current_weather"]
        temp = cw["temperature"]
        wind = cw["windspeed"]
        wc = int(cw.get("weathercode", 0))
        desc = _wmo_desc(wc)
        line = f"{label}: {temp}°C, {desc}, wind {wind} km/h"
        _save_cache(city, line)
        return line
    except Exception as e:
        print(f"[Weather] open-meteo failed: {e}")

    return f"{city}: Weather unavailable right now."


def fetch_weather(city: str = "Chennai") -> dict[str, Any]:
    """Legacy dict API for dashboard — uses format_weather_line."""
    line = format_weather_line(city)
    return {
        "city": city,
        "raw_line": line,
        "refreshed_at": time.strftime("%H:%M"),
        "_ts": time.time(),
    }
