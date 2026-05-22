from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import requests as _requests
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"

RECOMMENDED_MODELS = [
    {"name": "llama3.2",      "label": "Llama 3.2",        "size_est": "~2 GB",  "tag": "balanced",     "desc": "Meta's latest, best balance of speed and quality"},
    {"name": "llama3.1",      "label": "Llama 3.1",        "size_est": "~4 GB",  "tag": "balanced",     "desc": "Stronger reasoning than 3.2, needs more RAM"},
    {"name": "mistral",       "label": "Mistral 7B",       "size_est": "~4 GB",  "tag": "fast",         "desc": "Fast, great for summarisation and Q&A"},
    {"name": "gemma2",        "label": "Gemma 2",          "size_est": "~5 GB",  "tag": "fast",         "desc": "Google's open model, very fast responses"},
    {"name": "phi3",          "label": "Phi-3 Mini",       "size_est": "~2 GB",  "tag": "fast",         "desc": "Microsoft's tiny but surprisingly capable"},
    {"name": "deepseek-r1",   "label": "DeepSeek R1",      "size_est": "~7 GB",  "tag": "reasoning",    "desc": "Excellent for reasoning and step-by-step analysis"},
    {"name": "qwen2",         "label": "Qwen 2",           "size_est": "~4 GB",  "tag": "multilingual", "desc": "Strong multilingual support"},
    {"name": "codellama",     "label": "Code Llama",       "size_est": "~4 GB",  "tag": "code",         "desc": "Optimised for code understanding and generation"},
    {"name": "mixtral",       "label": "Mixtral 8x7B",     "size_est": "~26 GB", "tag": "powerful",     "desc": "Mixture of experts, handles complex questions well"},
    {"name": "solar",         "label": "Solar 10.7B",      "size_est": "~6 GB",  "tag": "balanced",     "desc": "Strong instruction following"},
    {"name": "neural-chat",   "label": "Neural Chat",      "size_est": "~4 GB",  "tag": "chat",         "desc": "Optimised for conversational use"},
    {"name": "tinyllama",     "label": "TinyLlama",        "size_est": "~600 MB","tag": "fast",         "desc": "Runs on very low RAM, ultra fast"},
]

DEFAULT_OLLAMA_PREFERENCES = [
    "llama3.2", "llama3.1", "mistral", "gemma2", "phi3", "deepseek-r1",
    "qwen2", "codellama", "mixtral", "solar", "neural-chat", "tinyllama",
]

def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_json(path: Path, data: dict[str, Any]) -> None:
    _ensure_config_dir()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_api_config() -> dict[str, Any]:
    return _load_json(API_KEYS_PATH)

def get_openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or get_api_config().get("openai_api_key")

def get_anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or get_api_config().get("anthropic_api_key")

def get_settings() -> dict[str, Any]:
    data = _load_json(SETTINGS_PATH)
    if not data:
        data = {
            "active_provider": "ollama",
            "active_model": "llama3.2",
            "home_assistant": {},
            "smart_devices": [],
        }
        _save_json(SETTINGS_PATH, data)
    return data

def save_settings(data: dict[str, Any]) -> None:
    _save_json(SETTINGS_PATH, data)

def get_active_model() -> dict[str, str]:
    settings = get_settings()
    provider = settings.get("active_provider", "ollama")
    model = settings.get("active_model", "llama3.2")
    if provider == "ollama":
        installed = {m["name"] for m in _ollama_installed_model_names()}
        if model not in installed:
            model = _auto_detect_ollama_model(installed)
            settings["active_model"] = model
            save_settings(settings)
    elif provider == "openai":
        if not get_openai_api_key():
            provider = "ollama"
            model = _auto_detect_ollama_model({m["name"] for m in _ollama_installed_model_names()})
            settings["active_provider"] = provider
            settings["active_model"] = model
            save_settings(settings)
    elif provider == "anthropic":
        if not get_anthropic_api_key():
            provider = "ollama"
            model = _auto_detect_ollama_model({m["name"] for m in _ollama_installed_model_names()})
            settings["active_provider"] = provider
            settings["active_model"] = model
            save_settings(settings)
    return {"provider": provider, "model": model}

def _auto_detect_ollama_model(installed: set[str]) -> str:
    for candidate in DEFAULT_OLLAMA_PREFERENCES:
        if candidate in installed:
            return candidate
    return next(iter(installed), "llama3.2")

def set_active_model(provider: str, model: str) -> dict[str, str]:
    provider = provider.lower()
    if provider not in {"ollama", "openai", "anthropic"}:
        raise ValueError("Unknown provider. Use: ollama, anthropic, openai")
    if provider == "ollama":
        installed = {m["name"] for m in _ollama_installed_model_names()}
        if model not in installed:
            raise ValueError(f"Ollama model '{model}' is not installed.")
    elif provider == "openai":
        if not get_openai_api_key():
            raise ValueError("OpenAI API key not configured.")
    elif provider == "anthropic":
        if not get_anthropic_api_key():
            raise ValueError("Anthropic API key not configured.")

    settings = get_settings()
    settings["active_provider"] = provider
    settings["active_model"] = model
    save_settings(settings)
    return {"provider": provider, "model": model}

def human_readable_size(value: int | None) -> str:
    if value is None:
        return "N/A"
    if value < 1024:
        return f"{value} B"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB"
    if value < 1024 ** 3:
        return f"{value / 1024 ** 2:.1f} MB"
    return f"{value / 1024 ** 3:.1f} GB"

def _extract_model_line_size(line: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)([KMGT]?B)", line, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "KB":
        return int(value * 1024)
    if unit == "MB":
        return int(value * 1024 ** 2)
    if unit == "GB":
        return int(value * 1024 ** 3)
    if unit == "TB":
        return int(value * 1024 ** 4)
    return int(value)

def _ollama_installed_model_names() -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    try:
        result = subprocess.run(
            ["ollama", "list", "--json"],
            capture_output=True, text=True, timeout=12,
        )
        if result.returncode == 0 and result.stdout:
            payload = json.loads(result.stdout)
            if isinstance(payload, dict) and "models" in payload:
                payload = payload["models"]
            for entry in payload if isinstance(payload, list) else []:
                name = entry.get("name") or entry.get("model")
                size = entry.get("size")
                updated_at = entry.get("updated_at") or entry.get("modified_at")
                if isinstance(size, str):
                    size = _extract_model_line_size(size)
                models.append({
                    "name": str(name),
                    "size": int(size) if isinstance(size, (int, float)) else None,
                    "modified_at": updated_at,
                })
    except Exception:
        pass

    if not models:
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.strip().split()
                    if not parts or parts[0].startswith("NAME"):
                        continue
                    name = parts[0]
                    size = None
                    modified_at = None
                    if len(parts) >= 2:
                        size = _extract_model_line_size(parts[-1])
                    models.append({"name": name, "size": size, "modified_at": modified_at})
        except Exception:
            pass

    unique = {}
    for model in models:
        if model["name"] not in unique:
            unique[model["name"]] = model
    return list(unique.values())

def get_ollama_model_catalog() -> dict[str, list[dict[str, Any]]]:
    installed = _ollama_installed_model_names()
    installed_names = {m["name"] for m in installed}
    installed = [
        {
            "name": item["name"],
            "size": human_readable_size(item.get("size")),
            "modified_at": item.get("modified_at") or "unknown",
            "installed": True,
        }
        for item in installed
    ]

    recommended = []
    for entry in RECOMMENDED_MODELS:
        recommended.append({
            **entry,
            "installed": entry["name"] in installed_names,
        })

    return {"installed": installed, "recommended": recommended}

def _ollama_chat(model: str, messages: list[dict], tools: list[dict] | None = None, timeout: int = 120) -> dict:
    """
    Calls Ollama's /api/chat endpoint.
    Returns the full response dict so callers can inspect tool_calls or message content.
    """
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools

    try:
        r = _requests.post(
            "http://localhost:11434/api/chat",
            json=body,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()
    except _requests.exceptions.ConnectionError:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")
    except _requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timed out after {timeout}s")


def _run_ollama_prompt(model: str, prompt: str, timeout: int = 60) -> str:
    """Legacy single-turn prompt — kept for unified_chat compatibility."""
    resp = _ollama_chat(model, [{"role": "user", "content": prompt}], timeout=timeout)
    return resp.get("message", {}).get("content", "").strip()


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    system_prompt: str = "",
    provider: str | None = None,
    model: str | None = None,
    timeout: int = 120,
) -> dict:
    """
    Main entry point for JarvisLocal.
    Sends a full conversation + tool definitions to the active model.
    Returns Ollama's raw response dict:
      {
        "message": {
          "role": "assistant",
          "content": "...",           # text reply (may be empty if tool called)
          "tool_calls": [             # present only when model wants to call a tool
            {
              "function": {
                "name": "open_app",
                "arguments": {"app_name": "Chrome"}
              }
            }
          ]
        }
      }
    """
    selection = get_active_model() if (provider is None or model is None) else {"provider": provider, "model": model}
    active_provider = selection["provider"]
    active_model    = selection["model"]

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    if active_provider == "ollama":
        return _ollama_chat(active_model, full_messages, tools=tools, timeout=timeout)

    # OpenAI-compatible fallback (tool calling works the same way)
    if active_provider == "openai":
        key = get_openai_api_key()
        if not key:
            raise RuntimeError("OpenAI API key not configured.")
        body = {
            "model": active_model,
            "messages": full_messages,
            "tools": [{"type": "function", "function": t} for t in tools],
            "tool_choice": "auto",
        }
        r = _requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body, timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        # Normalise to Ollama shape so callers don't need to branch
        choice = data["choices"][0]["message"]
        return {"message": choice}

    raise RuntimeError(f"Provider '{active_provider}' not supported for tool chat.")


def is_ollama_running() -> bool:
    """Quick health check — used by setup panel."""
    try:
        r = _requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def pull_model(model: str, progress_callback: Any | None = None, stop_event: threading.Event | None = None) -> None:
    proc = subprocess.Popen(
        ["ollama", "pull", model],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if stop_event and stop_event.is_set():
                proc.kill()
                break
            if progress_callback:
                progress_callback(line.rstrip())
    finally:
        proc.wait(timeout=30)
        if progress_callback:
            progress_callback("__complete__")

def remove_model(model: str) -> None:
    result = subprocess.run(["ollama", "rm", model], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Failed to remove model {model}")

def unified_chat(system_prompt: str, user_prompt: str, provider: str | None = None, model: str | None = None) -> str:
    selection = get_active_model() if provider is None or model is None else {"provider": provider, "model": model}
    provider = selection["provider"]
    model = selection["model"]

    prompt = f"{system_prompt}\n\n{user_prompt}"
    if provider == "ollama":
        return _run_ollama_prompt(model, prompt)

    if provider == "openai":
        key = get_openai_api_key()
        if not key:
            raise RuntimeError("OpenAI API key not configured.")
        import requests
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 512,
        }
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    if provider == "anthropic":
        key = get_anthropic_api_key()
        if not key:
            raise RuntimeError("Anthropic API key not configured.")
        import requests
        body = {
            "model": model,
            "prompt": f"\n\nHuman: {user_prompt}\n\nAssistant:",
            "max_tokens_to_sample": 512,
            "temperature": 0.7,
        }
        r = requests.post(
            "https://api.anthropic.com/v1/complete",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("completion", "").strip()

    raise RuntimeError("Unknown provider. Use: ollama, anthropic, openai")
