"""Market tracker — watchlist DB operations + live price fetch."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests as _req

try:
    from core.paths import get_project_root
    BASE = get_project_root()
except ImportError:
    def _base() -> Path:
        p = Path(__file__).resolve()
        for _ in range(6):
            if (p / "config").exists() and (p / "main.py").exists():
                return p
            p = p.parent
        return Path(__file__).resolve().parent.parent

    BASE = _base()


TOOL_SPEC = {
    "name": "market_tracker",
    "description": (
        "Tracks share market symbols and manages a watchlist. "
        "Can add/remove from watchlist, show watchlist with current prices, "
        "open broker websites (Groww, Zerodha), and check current price of any symbol."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "show_watchlist", "open_broker", "get_price"],
                "description": "The action to perform.",
            },
            "symbol": {
                "type": "string",
                "description": "Stock symbol or name (e.g. ITC, RELIANCE, GOLDBEES).",
            },
            "broker": {
                "type": "string",
                "description": "Broker name (groww, zerodha, upstox, angelone).",
            },
        },
        "required": ["action"],
    },
}

_ALIASES: dict[str, str] = {
    "itc": "ITC.NS",
    "itc jacuzzi": "ITC.NS",
    "reliance": "RELIANCE.NS",
    "tata motors": "TATAMOTORS.NS",
    "tatamotors": "TATAMOTORS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "tcs": "TCS.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "sbi": "SBIN.NS",
    "wipro": "WIPRO.NS",
    "bajaj": "BAJFINANCE.NS",
    "ipc": "INDIACEM.NS",
    "india cement": "INDIACEM.NS",
    "nippon gold bees": "GOLDBEES.NS",
    "goldbees": "GOLDBEES.NS",
    "nippon": "GOLDBEES.NS",
    "gold bees": "GOLDBEES.NS",
    "nifty": "^NSEI",
    "sensex": "^BSESN",
    "ongc": "ONGC.NS",
    "coal india": "COALINDIA.NS",
    "coalindia": "COALINDIA.NS",
    "adani": "ADANIPORTS.NS",
    "irctc": "IRCTC.NS",
    "zomato": "ZOMATO.NS",
}


def _normalise_symbol(raw: str) -> str:
    clean = raw.strip().lower()
    if clean in _ALIASES:
        return _ALIASES[clean]
    upper = raw.strip().upper()
    if upper.endswith(".NS") or upper.endswith(".BO") or upper.startswith("^"):
        return upper
    if re.match(r"^[A-Z]{2,12}$", upper):
        return f"{upper}.NS"
    return upper


def _get_price(symbol: str) -> dict:
    sym = _normalise_symbol(symbol)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = _req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", price)
        change = round(price - prev, 2)
        pct = round((change / prev) * 100, 2) if prev else 0
        name = meta.get("shortName", sym)
        return {
            "symbol": sym,
            "name": name,
            "price": round(price, 2),
            "change": change,
            "change_pct": pct,
            "currency": meta.get("currency", "INR"),
            "ok": True,
        }
    except Exception as e:
        return {"symbol": sym, "price": None, "ok": False, "error": str(e)}


def _db():
    from db.database import get_db
    return get_db()


def _add_to_db(symbol: str) -> bool:
    sym = _normalise_symbol(symbol)
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, added_at) VALUES (?, datetime('now'))",
            (sym,),
        )
        added = cur.rowcount > 0
        conn.commit()
        conn.close()
        return added
    except Exception as e:
        print(f"[Market] DB add error: {e}")
        return False


def _remove_from_db(symbol: str) -> bool:
    sym = _normalise_symbol(symbol)
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
        removed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return removed
    except Exception as e:
        print(f"[Market] DB remove error: {e}")
        return False


def _get_all_symbols() -> list[str]:
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM watchlist ORDER BY added_at")
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[Market] DB read error: {e}")
        return []


def _refresh_dashboard(player) -> None:
    try:
        if player and hasattr(player, "_win") and hasattr(player._win, "_refresh_side"):
            player._win._refresh_side()
    except Exception as e:
        print(f"[Market] Dashboard refresh error: {e}")


def run(parameters: dict | None = None, player=None, speak=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "show_watchlist").lower().strip()
    symbol = (params.get("symbol") or "").strip()
    broker = (params.get("broker") or "groww").lower()

    if action == "add":
        if not symbol:
            return "Please specify a symbol to add. E.g. ITC, RELIANCE, GOLDBEES"
        syms = [s.strip() for s in re.split(r"[,;]", symbol) if s.strip()]
        results = []
        for s in syms:
            added = _add_to_db(s)
            norm = _normalise_symbol(s)
            if added:
                results.append(f"✅ {norm} added to watchlist")
            else:
                results.append(f"ℹ {norm} already in watchlist")
        _refresh_dashboard(player)
        msg = "\n".join(results)
        if player and hasattr(player, "write_log"):
            player.write_log(f"SYS: {msg}")
        return msg

    if action == "remove":
        if not symbol:
            return "Specify a symbol to remove."
        removed = _remove_from_db(symbol)
        norm = _normalise_symbol(symbol)
        msg = f"{'✅ Removed' if removed else 'ℹ Not found'}: {norm}"
        _refresh_dashboard(player)
        return msg

    if action == "get_price":
        if not symbol:
            return "Specify a symbol, e.g. get_price for ITC"
        syms = [s.strip() for s in re.split(r"[,;]", symbol) if s.strip()]
        lines = []
        for s in syms:
            d = _get_price(s)
            if d["ok"]:
                arrow = "▲" if d["change"] >= 0 else "▼"
                lines.append(
                    f"{d['symbol']}: ₹{d['price']} {arrow}{abs(d['change'])} ({d['change_pct']}%)"
                )
            else:
                lines.append(f"{d['symbol']}: unavailable ({d.get('error', '')})")
        return "\n".join(lines) or "No data."

    if action in ("show_watchlist", "list", "show"):
        syms = _get_all_symbols()
        if not syms:
            return "Watchlist is empty. Say 'add ITC to watchlist' to get started."
        lines = [f"📊 Watchlist ({len(syms)} stocks):"]
        for s in syms:
            d = _get_price(s)
            if d["ok"]:
                arrow = "▲" if d["change"] >= 0 else "▼"
                lines.append(
                    f"  {s}: ₹{d['price']} {arrow}{abs(d['change'])} ({d['change_pct']}%)"
                )
            else:
                lines.append(f"  {s}: price unavailable")
        _refresh_dashboard(player)
        return "\n".join(lines)

    if action == "open_broker":
        urls = {
            "groww": "https://groww.in/stocks",
            "zerodha": "https://kite.zerodha.com",
            "upstox": "https://upstox.com",
            "angelone": "https://www.angelone.in",
        }
        url = urls.get(broker, "https://groww.in")
        try:
            import webbrowser
            webbrowser.open(url)
            return f"Opened {broker.title()} in browser."
        except Exception as e:
            return f"Could not open browser: {e}"

    return f"Unknown market action: {action}. Use: add, remove, get_price, show_watchlist, open_broker"


def market_tracker(params: dict | None = None, player=None) -> str:
    return run(parameters=params, player=player)
