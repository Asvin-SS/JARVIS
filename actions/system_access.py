"""Full system access — open apps, run commands, read/write files."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_APP_MAP = {
    "vs code": ["code"],
    "vscode": ["code"],
    "vs": ["code"],
    "visual studio": ["devenv"],
    "notepad": ["notepad"],
    "explorer": ["explorer"],
    "chrome": ["chrome", "google-chrome"],
    "edge": ["msedge", "microsoft-edge"],
    "firefox": ["firefox"],
    "teams": ["teams"],
    "outlook": ["outlook"],
    "word": ["winword"],
    "excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "cmd": ["cmd"],
    "powershell": ["powershell"],
    "terminal": ["wt"],
    "task manager": ["taskmgr"],
    "calculator": ["calc"],
    "paint": ["mspaint"],
    "snipping tool": ["snippingtool"],
}


def open_application(name: str, args: list[str] | None = None) -> str:
    key = name.lower().strip()
    candidates = _APP_MAP.get(key, [key])

    for exe in candidates:
        try:
            cmd = [exe] + (args or [])
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return f"Opened {name}."
        except Exception:
            continue

    if sys.platform == "win32":
        try:
            os.startfile(name)
            return f"Opened {name}."
        except Exception:
            pass

    return f"Could not open '{name}'. Is it installed?"


def open_file_in_app(file_path: str, app: str | None = None) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if app:
        return open_application(app, [str(p)])
    try:
        os.startfile(str(p))
        return f"Opened {p.name}"
    except Exception as e:
        try:
            subprocess.Popen(["explorer", str(p)], shell=True)
            return f"Opened {p.name} with explorer"
        except Exception as e2:
            return f"Could not open file: {e2}"


def open_folder(folder_path: str) -> str:
    p = Path(folder_path)
    if not p.exists():
        return f"Folder not found: {folder_path}"
    try:
        subprocess.Popen(["explorer", str(p)], shell=True)
        return f"Opened folder: {p}"
    except Exception as e:
        return f"Could not open folder: {e}"


def run_command(cmd: str, cwd: str | None = None, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if result.returncode != 0:
            return f"Command failed (code {result.returncode}):\n{err or out}"
        return out or "Command completed."
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Command error: {e}"


def read_file(file_path: str, max_chars: int = 8000) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n...\n[truncated — {len(content)} total chars]"
        return content
    except Exception as e:
        return f"Could not read file: {e}"


def write_file(file_path: str, content: str, append: bool = False) -> str:
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        if append:
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
            return f"Appended to {p.name}"
        p.write_text(content, encoding="utf-8")
        return f"Written to {p.name}"
    except Exception as e:
        return f"Could not write file: {e}"


def list_directory(folder_path: str, pattern: str = "*") -> str:
    p = Path(folder_path)
    if not p.exists():
        return f"Folder not found: {folder_path}"
    try:
        items = sorted(p.glob(pattern))[:50]
        lines = []
        for item in items:
            tag = "📁" if item.is_dir() else "📄"
            lines.append(f"{tag} {item.name}")
        return "\n".join(lines) or "Empty directory."
    except Exception as e:
        return f"Could not list directory: {e}"


def open_vs_code_with_folder(folder_path: str) -> str:
    p = Path(folder_path)
    if not p.exists():
        return f"Folder not found: {folder_path}"
    try:
        subprocess.Popen(
            ["code", str(p)],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened VS Code at {p}"
    except Exception as e:
        return f"Could not open VS Code: {e}"


def system_access(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "").lower().strip()
    path = parameters.get("path") or parameters.get("file_path") or ""
    content = parameters.get("content") or ""
    command = parameters.get("command") or ""
    app_name = parameters.get("app_name") or parameters.get("name") or ""
    folder = parameters.get("folder") or ""

    if action in ("open_app", "launch", "start", "open"):
        if path and Path(path).exists():
            result = open_file_in_app(path, app_name or None)
        elif app_name:
            result = open_application(app_name)
        elif path:
            result = open_application(path)
        else:
            result = "Specify app_name or path."

    elif action in ("open_folder", "explore"):
        result = open_folder(path or folder)

    elif action in ("open_vscode", "open_vs_code", "code"):
        result = open_vs_code_with_folder(path or folder or ".")

    elif action in ("run", "execute", "shell", "cmd"):
        result = run_command(command or path, cwd=folder or None)

    elif action in ("read", "read_file"):
        result = read_file(path)

    elif action in ("write", "write_file", "save"):
        result = write_file(path, content)

    elif action in ("append",):
        result = write_file(path, content, append=True)

    elif action in ("list", "ls", "dir"):
        result = list_directory(path or folder)

    else:
        result = f"Unknown system_access action: {action}. Use: open_app, open_folder, run, read, write, list"

    if player and hasattr(player, "write_log"):
        player.write_log(f"SYS: {result[:200]}")
    if speak and len(result) < 200:
        speak(result)
    return result
