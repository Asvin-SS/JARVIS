"""Optimizely Configured Commerce coding agent."""
from __future__ import annotations

import re
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "optimizely"


def _load_knowledge() -> str:
    parts = []
    for f in _KNOWLEDGE_DIR.glob("*.md"):
        try:
            parts.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n\n".join(parts)


def optimizely_agent(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    error_text = (p.get("error") or p.get("instruction") or "").strip()
    ticket_id = p.get("ticket_id") or ""
    open_docs = p.get("open_docs", False)

    if player:
        player.write_log("SYS: Optimizely agent activated...")

    if not error_text:
        try:
            from actions.screen_processor import _capture_screen
            from core.vision_backend import analyze_image
            img, mime = _capture_screen()
            error_text = analyze_image(img, "Extract the exact error message and stack trace.", mime)
        except Exception as e:
            error_text = f"Could not read screen: {e}"

    knowledge = _load_knowledge()
    prompt = f"""You are an expert Optimizely Configured Commerce (.NET) developer.

## Project Knowledge Base
{knowledge[:2000]}

## Error / Issue
{error_text[:1500]}

## Ticket
{ticket_id}

Provide:
1. Root cause (1 sentence)
2. Exact fix (code diff or steps)
3. Which file/handler to modify
4. How to verify the fix

Be specific to OCC architecture."""

    from llm_client import get_anthropic_api_key, unified_chat
    key = get_anthropic_api_key()
    result = ""
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            result = msg.content[0].text
        except Exception:
            result = unified_chat("You are an OCC expert.", prompt)
    else:
        result = unified_chat("You are an expert Optimizely developer.", prompt)

    if open_docs:
        try:
            from actions.browser_control import browser_control
            search = re.sub(r"\s+", "+", error_text[:80])
            browser_control({
                "action": "open",
                "url": f"https://support.optimizely.com/hc/en-us/search?utf8=✓&query={search}",
            })
        except Exception:
            pass

    if len(result) < 200:
        try:
            from actions.coding_agent import ask_claude_in_browser
            result += "\n\n" + ask_claude_in_browser(error_text[:400], knowledge[:400], player, speak)
        except Exception:
            pass

    if player:
        player.write_log(f"Jarvis (OCC): {result[:800]}")
    if speak:
        speak("I've analyzed the Optimizely issue. Check the activity log.")
    return result
