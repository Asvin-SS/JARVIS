"""
Local coding assistant bridge — Ollama-first, optional Aider CLI if installed.
Inspired by https://github.com/Aider-AI/aider (runs via subprocess when available).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


def _aider_available() -> bool:
    return shutil.which("aider") is not None


def _ollama_edit(file_path: Path, instruction: str) -> str:
    """Apply an edit using local Ollama chat (no cloud key required)."""
    if not file_path.exists():
        return f"File not found: {file_path}"

    code = file_path.read_text(encoding="utf-8", errors="replace")
    from llm_client import chat_with_tools, get_active_model

    if not __import__("llm_client").is_ollama_running():
        return "Ollama is not running. Start it with: ollama serve"

    prompt = (
        f"You are a coding assistant. Edit the file below per the instruction.\n"
        f"Return ONLY the full updated file content — no markdown fences, no explanation.\n\n"
        f"Instruction: {instruction}\n\n"
        f"File: {file_path.name}\n```\n{code[:12000]}\n```"
    )
    resp = chat_with_tools(
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        system_prompt="You output complete source files only.",
        stream=False,
    )
    msg = resp.get("message", {}) if isinstance(resp, dict) else {}
    new_code = (msg.get("content") or "").strip()
    new_code = re.sub(r"^```[a-zA-Z]*\n?", "", new_code)
    new_code = re.sub(r"\n?```\s*$", "", new_code)
    if len(new_code) < 10:
        return "Model returned empty edit — try a clearer instruction."

    backup = file_path.with_suffix(file_path.suffix + ".jarvis.bak")
    backup.write_text(code, encoding="utf-8")
    file_path.write_text(new_code, encoding="utf-8")
    model = get_active_model()["model"]
    return f"Updated {file_path.name} via Ollama ({model}). Backup: {backup.name}"


def _aider_run(file_path: Path, instruction: str) -> str:
    cmd = [
        "aider",
        "--yes",
        "--no-auto-commits",
        "--message", instruction,
        str(file_path),
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(file_path.parent),
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return f"Aider applied edit to {file_path.name}.\n{out[-800:]}"
        return f"Aider failed ({r.returncode}): {out[-600:]}"
    except subprocess.TimeoutExpired:
        return "Aider timed out after 5 minutes."
    except Exception as e:
        return f"Aider error: {e}"


def coding_bridge(parameters: dict, player=None, speak=None) -> str:
    """
    TOOL: debug/edit code locally.
    parameters: file_path, instruction, use_aider (optional bool)
    """
    p = parameters or {}
    file_path = (p.get("file_path") or "").strip()
    instruction = (p.get("instruction") or p.get("description") or "").strip()
    if not file_path or not instruction:
        return "Need file_path and instruction (e.g. fix the null reference on line 42)."

    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    use_aider = p.get("use_aider", True)
    if use_aider and _aider_available():
        if player:
            player.write_log(f"SYS: Aider editing {path.name}…")
        return _aider_run(path, instruction)

    if player:
        player.write_log(f"SYS: Ollama editing {path.name}…")
    return _ollama_edit(path, instruction)


TOOL_SPEC = {
    "name": "coding_bridge",
    "description": (
        "Edit or debug a source file locally using Ollama (or Aider if installed). "
        "Use for bug fixes, refactors, and small feature changes in the codebase."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to edit"},
            "instruction": {"type": "string", "description": "What to change or fix"},
            "use_aider": {"type": "boolean", "description": "Prefer Aider CLI if installed"},
        },
        "required": ["file_path", "instruction"],
    },
}
