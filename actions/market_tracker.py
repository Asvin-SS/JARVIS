import yfinance as yf
import webbrowser
from db.database import get_db
from datetime import datetime

TOOL_SPEC = {
    "name": "market_tracker",
    "description": (
        "Tracks share market symbols and manages a watchlist. "
        "Can add to watchlist, show watchlist with current prices, "
        "open broker websites (Groww, Zerodha), and check current price of any symbol."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "show_watchlist", "open_broker", "get_price"],
                "description": "The action to perform."
            },
            "symbol": {
                "type": "string",
                "description": "The stock symbol (e.g., RELIANCE.NS, TCS.NS, AAPL)."
            },
            "broker": {
                "type": "string",
                "description": "The broker name (Groww, Zerodha)."
            },
            "label": {
                "type": "string",
                "description": "Optional label for the watchlist item."
            }
        },
        "required": ["action"]
    }
}

def run(parameters: dict, player=None) -> str:
    action = parameters.get("action")
    symbol = parameters.get("symbol")
    broker = parameters.get("broker")
    label  = parameters.get("label")

    if action == "add":
        if not symbol:
            return "Please provide a symbol to add."
        try:
            conn = get_db()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO watchlist (symbol, label, added_at) VALUES (?, ?, ?)",
                (symbol.upper(), label or symbol.upper(), now)
            )
            conn.commit()
            conn.close()
            return f"Added {symbol.upper()} to your watchlist."
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                return f"{symbol.upper()} is already in your watchlist."
            return f"Failed to add symbol: {e}"

    elif action == "show_watchlist":
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlist")
            symbols = [row[0] for row in cursor.fetchall()]
            conn.close()

            if not symbols:
                return "Your watchlist is empty."

            results = []
            for sym in symbols:
                try:
                    ticker = yf.Ticker(sym)
                    info = ticker.fast_info
                    price = info.last_price
                    # Use change if available
                    prev_close = info.previous_close
                    change = ((price - prev_close) / prev_close * 100) if prev_close else 0
                    results.append(f"{sym}: ₹{price:.2f} ({'+' if change >=0 else ''}{change:.2f}%)")
                except Exception:
                    results.append(f"{sym}: Price unavailable")
            
            return "Watchlist:\n" + "\n".join(results)
        except Exception as e:
            return f"Failed to fetch watchlist: {e}"

    elif action == "open_broker":
        if not broker:
            return "Please specify a broker (e.g., Groww, Zerodha)."
        
        urls = {
            "groww": "https://groww.in",
            "zerodha": "https://kite.zerodha.com",
        }
        url = urls.get(broker.lower())
        if url:
            webbrowser.open(url)
            return f"Opening {broker} in your browser."
        else:
            # Try to open as a general URL or search
            webbrowser.open(f"https://www.google.com/search?q={broker}")
            return f"Broker {broker} not specifically mapped. Searching for it..."

    elif action == "get_price":
        if not symbol:
            return "Please provide a symbol to check."
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = info.last_price
            return f"{symbol.upper()} is currently trading at ₹{price:.2f}."
        except Exception as e:
            return f"Failed to fetch price for {symbol}: {e}"

    return "Unknown action for market_tracker."
