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

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")

def get_active_tasks():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'active' ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_watchlist():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watchlist")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_session(started_at, summary=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (started_at, summary) VALUES (?, ?)", (started_at, summary))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id

if __name__ == "__main__":
    init_db()
