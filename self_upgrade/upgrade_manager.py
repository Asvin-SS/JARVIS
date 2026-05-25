"""Safe self-upgrade — git branches and sandbox copies."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def create_change_branch(description: str) -> str:
    slug = description.lower()[:40].replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    branch = f"jarvis-auto/{timestamp}-{slug}"
    subprocess.run(["git", "checkout", "-b", branch], cwd=BASE_DIR, check=True, capture_output=True)
    return branch


def commit_change(message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, check=True)
    result = subprocess.run(
        ["git", "commit", "-m", f"[Jarvis Auto] {message}"],
        cwd=BASE_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return "Nothing to commit."
    h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True)
    return h.stdout.strip()


def create_sandbox(feature_name: str) -> Path:
    slug = feature_name.lower().replace(" ", "_")[:30]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    sandbox_path = BASE_DIR.parent / f"Mark-XXXIX_sandbox_{slug}_{timestamp}"
    ignore = shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", ".git", "logs", "db", "*.db")
    shutil.copytree(BASE_DIR, sandbox_path, ignore=ignore)
    return sandbox_path


def apply_upgrade(description: str, file_changes: dict[str, str], player=None) -> str:
    try:
        branch = create_change_branch(description)
    except Exception as e:
        return f"Git branch failed (init repo first): {e}"
    changed = []
    for rel_path, content in file_changes.items():
        target = BASE_DIR / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changed.append(rel_path)
    commit_hash = commit_change(description)
    msg = (
        f"Changes on branch '{branch}' (commit {commit_hash}).\n"
        f"Modified: {', '.join(changed)}\n"
        f"Test: git checkout {branch} && python main.py"
    )
    if player:
        player.write_log(f"SYS: {msg}")
    return msg


def github_feature_search(query: str) -> list[dict]:
    import requests
    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": f"{query} jarvis assistant python", "sort": "stars", "per_page": 5},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        items = r.json().get("items", [])
        return [
            {"name": i["full_name"], "stars": i["stargazers_count"],
             "description": i["description"], "url": i["html_url"]}
            for i in items
        ]
    except Exception as e:
        return [{"error": str(e)}]


def self_upgrade_tool(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    desc = p.get("description", "upgrade")
    if p.get("search_github"):
        q = p.get("github_query") or desc
        hits = github_feature_search(q)
        lines = [f"{h.get('name')}: {h.get('url')}" for h in hits if "error" not in h]
        return "\n".join(lines) or str(hits)
    return apply_upgrade(desc, p.get("file_changes") or {}, player=player)
