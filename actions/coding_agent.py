"""
Coding agent: screen capture + file reading + Aider/Ollama fix.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def ask_claude_in_browser(question: str, context: str = "", player=None, speak=None) -> str:
    """Open claude.ai; copy question to clipboard when pyperclip available."""
    full_q = f"{context}\n\n{question}" if context else question
    clipboard_msg = "Paste your question in Claude."
    try:
        import pyperclip
        pyperclip.copy(full_q[:3000])
        clipboard_msg = "Question copied to clipboard — paste it in Claude."
    except ImportError:
        clipboard_msg = "Install pyperclip for auto-clipboard: pip install pyperclip"

    try:
        from actions.browser_control import browser_control
        browser_control({"action": "open", "url": "https://claude.ai/new"})
    except Exception as e:
        return f"Browser open failed: {e}"

    msg = f"Opening Claude.ai. {clipboard_msg}"
    if player:
        player.write_log(f"SYS: {msg}")
    if speak:
        speak("Opening Claude in the browser. Your question is ready to paste.")
    return msg


def coding_agent(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    instruction = (p.get("instruction") or p.get("description") or "").strip()
    file_path = (p.get("file_path") or "").strip()
    use_screen = p.get("use_screen", True)

    if player:
        player.write_log("SYS: Coding agent started...")

    screen_text = ""
    if use_screen and not instruction:
        try:
            from actions.screen_processor import _capture_screen
            from core.vision_backend import analyze_image
            img_bytes, mime = _capture_screen()
            screen_text = analyze_image(
                img_bytes,
                "Extract any error messages, stack traces, or code visible. Be precise.",
                mime,
            )
            if player:
                player.write_log(f"SYS: Screen read — {screen_text[:200]}")
        except Exception as e:
            screen_text = f"Screen capture failed: {e}"

    combined = f"{instruction}\n{screen_text}".strip()
    if not combined:
        return "Tell me what to fix, or let me read your screen for the error."

    if not file_path:
        path_pattern = re.compile(
            r'(?:File|in|at)\s+"?([A-Za-z]:\\[^\s\'"]+\.(?:py|cs|ts|js|jsx|tsx|html|css))"?',
            re.IGNORECASE,
        )
        m = path_pattern.search(combined)
        if m:
            file_path = m.group(1)

    if file_path and _aider_available():
        return _fix_with_aider(file_path, combined, player, speak)

    return _fix_with_ollama(combined, file_path, player, speak)


def _aider_available() -> bool:
    try:
        r = subprocess.run(["aider", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _fix_with_aider(file_path: str, instruction: str, player=None, speak=None) -> str:
    if player:
        player.write_log(f"SYS: Aider — {Path(file_path).name}")
    if speak:
        speak(f"Using Aider to fix {Path(file_path).name}")
    try:
        cmd = ["aider", "--no-auto-commits", "--yes", file_path, "--message", instruction[:800]]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (result.stdout or "") + (result.stderr or "")
        if player:
            player.write_log(f"Aider: {out[:400]}")
        return out[:1000] or "Aider finished."
    except subprocess.TimeoutExpired:
        return "Aider timed out after 2 minutes."
    except Exception as e:
        return f"Aider failed: {e}"


def _fix_with_ollama(instruction: str, file_path: str, player=None, speak=None) -> str:
    from llm_client import unified_chat, is_ollama_running

    if not is_ollama_running():
        return ask_claude_in_browser(instruction[:500], "", player, speak)

    file_content = ""
    if file_path and Path(file_path).exists():
        try:
            file_content = Path(file_path).read_text(encoding="utf-8", errors="ignore")[:4000]
        except Exception:
            pass

    prompt = f"""You are a senior developer. Fix the following issue.

Error / Instruction:
{instruction[:1000]}

File content ({file_path or 'n/a'}):
{file_content}

Provide ONLY the corrected code or a specific diff. Be concise."""

    result = unified_chat("You are an expert developer.", prompt)
    if player:
        player.write_log(f"Jarvis: {result[:600]}")
    if speak:
        speak("I've analyzed the issue. Check the activity log for the fix.")

    if len(result) < 200:
        browser_result = ask_claude_in_browser(instruction[:500], file_content[:500], player, speak)
        return f"{result}\n\n[Fallback] {browser_result}"
    return result
