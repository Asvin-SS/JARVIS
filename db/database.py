import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime

def get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent

DB_DIR = get_base_dir() / "db"
DB_PATH = DB_DIR / "jarvis.db"

def get_db():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # Conversation history
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        role TEXT NOT NULL, -- 'user' or 'assistant'
        content TEXT NOT NULL,
        session_id TEXT
    )
    ''')

    # Task tracking
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'active', -- active | completed | paused
        category TEXT, -- work | personal | trading | reminder | etc
        progress_notes TEXT -- JSON array of update strings
    )
    ''')

    # Share market watchlist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL UNIQUE,
        label TEXT,
        added_at TEXT NOT NULL,
        notes TEXT
    )
    ''')

    # User preferences
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS preferences (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')

    # Session log (for greeting context)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        summary TEXT -- LLM-generated one-line summary of what was done
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS self_built_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        description TEXT,
        requested_by TEXT
    )
    ''')

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")
    ensure_watchlist_table()


def ensure_watchlist_table(conn=None):
    close = False
    if conn is None:
        conn = get_db()
        close = True
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol   TEXT    UNIQUE NOT NULL,
            label    TEXT,
            added_at TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    if close:
        conn.close()


def get_watchlist() -> list[dict]:
    conn = get_db()
    ensure_watchlist_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT symbol, label, added_at FROM watchlist ORDER BY added_at")
    rows = [{"symbol": r[0], "label": r[1] or r[0], "added_at": r[2]} for r in cur.fetchall()]
    conn.close()
    return rows


def add_watchlist_symbol(symbol: str, label: str | None = None) -> bool:
    sym = symbol.upper().strip()
    conn = get_db()
    ensure_watchlist_table(conn)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO watchlist (symbol, label, added_at) VALUES (?, ?, datetime('now'))",
        (sym, label or sym),
    )
    added = cur.rowcount > 0
    conn.commit()
    conn.close()
    return added


def get_active_tasks():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE status = 'active' AND category != 'test' ORDER BY updated_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_watchlist_symbol(symbol: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper().strip(),))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def add_session(started_at, summary=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (started_at, summary) VALUES (?, ?)", (started_at, summary))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


def get_preference(key: str, default: str | None = None) -> str | None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM preferences WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_preference(key: str, value: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO preferences (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def save_task(title: str, description: str = "", category: str = "personal") -> int:
    now = datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO tasks (created_at, updated_at, title, description, status, category)
           VALUES (?, ?, ?, ?, 'active', ?)""",
        (now, now, title, description, category),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def complete_task(title_substring: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        """UPDATE tasks SET status = 'completed', updated_at = ?
           WHERE status = 'active' AND title LIKE ?""",
        (now, f"%{title_substring}%"),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def log_conversation(role: str, content: str, session_id: str | None = None) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversations (timestamp, role, content, session_id) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), role, content, session_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
