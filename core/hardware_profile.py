"""Scan local hardware and pick the best Ollama model for this machine."""
from __future__ import annotations

import json
import subprocess
import threading
from typing import Any, Callable

import psutil

try:
    from core.logging_setup import setup_logging
    _log = setup_logging("hardware")
except ImportError:
    _log = None

# model pull name -> minimum RAM (GB) to run comfortably
_MODEL_TIERS: list[tuple[str, float, str]] = [
    ("mixtral:latest", 24.0, "Mixtral 8x7B — best quality on high-RAM systems"),
    ("llama3.1:latest", 14.0, "Llama 3.1 — strong reasoning"),
    ("mistral:latest", 8.0, "Mistral — fast balanced default"),
    ("llama3.2:latest", 6.0, "Llama 3.2 — good speed/quality on mid-range"),
    ("phi3:latest", 4.0, "Phi-3 Mini — lightweight but capable"),
    ("tinyllama:latest", 2.0, "TinyLlama — minimal RAM systems"),
]

_CODING_TIERS: list[tuple[str, float]] = [
    ("codellama:latest", 8.0),
    ("deepseek-coder:latest", 8.0),
    ("mistral:latest", 6.0),
    ("llama3.2:latest", 4.0),
]


def scan_hardware() -> dict[str, Any]:
    """Return RAM, CPU, GPU summary for model routing."""
    mem = psutil.virtual_memory()
    ram_gb = round(mem.total / (1024 ** 3), 1)
    cpu_cores = psutil.cpu_count(logical=True) or 4
    gpu_name, gpu_vram = _detect_gpu()
    return {
        "ram_gb": ram_gb,
        "ram_available_gb": round(mem.available / (1024 ** 3), 1),
        "cpu_cores": cpu_cores,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram,
        "os": __import__("platform").system(),
    }


def _detect_gpu() -> tuple[str, float]:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            line = r.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            name = parts[0]
            vram = float(parts[1]) / 1024 if len(parts) > 1 else 0.0
            return name, round(vram, 1)
    except Exception:
        pass
    return "none", 0.0


def recommend_models(profile: dict[str, Any] | None = None) -> dict[str, str]:
    """Pick general + coding model names for this hardware."""
    p = profile or scan_hardware()
    ram = float(p.get("ram_gb", 8))
    general = _MODEL_TIERS[-1][0]
    for model, min_ram, _ in _MODEL_TIERS:
        if ram >= min_ram:
            general = model
            break
    coding = general
    for model, min_ram in _CODING_TIERS:
        if ram >= min_ram:
            coding = model
            break
    return {"general": general, "coding": coding}


def hardware_summary(profile: dict[str, Any] | None = None) -> str:
    p = profile or scan_hardware()
    rec = recommend_models(p)
    gpu = p.get("gpu_name", "none")
    if gpu != "none":
        gpu_part = f", GPU {gpu} ({p.get('gpu_vram_gb', 0)} GB VRAM)"
    else:
        gpu_part = ", CPU-only inference"
    return (
        f"Hardware: {p['ram_gb']} GB RAM, {p['cpu_cores']} cores{gpu_part}. "
        f"Recommended model: {rec['general']} (coding: {rec['coding']})."
    )


def _installed_models() -> set[str]:
    try:
        from llm_client import _ollama_installed_model_names
        return {m["name"] for m in _ollama_installed_model_names()}
    except Exception:
        return set()


def apply_hardware_model(
    on_log: Callable[[str], None] | None = None,
    auto_pull: bool = True,
) -> dict[str, Any]:
    """
    Set active Ollama model from hardware scan if auto_hardware_model is enabled.
    Returns {profile, recommended, applied, pulled}.
    """
    from llm_client import get_settings, save_settings, is_ollama_running

    settings = get_settings()
    if not settings.get("auto_hardware_model", True):
        return {"skipped": True}

    profile = scan_hardware()
    rec = recommend_models(profile)
    target = rec["general"]
    installed = _installed_models()
    applied = target
    pulled = False

    def log(msg: str):
        if on_log:
            on_log(msg)
        if _log:
            _log.info(msg)
        print(f"[Hardware] {msg}")

    if not is_ollama_running():
        log("Ollama offline — hardware model selection deferred.")
        settings["hardware_profile"] = profile
        settings["hardware_recommended"] = rec
        save_settings(settings)
        return {"profile": profile, "recommended": rec, "applied": None, "pulled": False}

    # Use best installed match if target not present
    if target not in installed:
        for model, min_ram, _ in _MODEL_TIERS:
            if float(profile["ram_gb"]) >= min_ram and model in installed:
                applied = model
                break
        else:
            applied = next(iter(installed), target) if installed else target

        if applied not in installed and auto_pull and settings.get("auto_pull_model", True):
            log(f"Pulling recommended model {target}…")
            try:
                from llm_client import pull_model
                def _plog(pct, spd):
                    if pct == "__complete__":
                        return
                    if isinstance(pct, int):
                        log(f"Pull {target}: {pct}%")
                pull_model(target, progress_callback=_plog)
                applied = target
                pulled = True
            except Exception as e:
                log(f"Pull failed ({e}) — using {applied or 'default'}.")

    settings["active_provider"] = "ollama"
    settings["active_model"] = applied
    settings["model_roles"] = {
        "coding": rec["coding"] if rec["coding"] in (_installed_models() | {applied}) else applied,
        "reasoning": applied,
        "summary": applied,
        "vision": settings.get("vision_model", "llava:latest"),
    }
    settings["hardware_profile"] = profile
    settings["hardware_recommended"] = rec
    save_settings(settings)
    log(hardware_summary(profile))
    return {"profile": profile, "recommended": rec, "applied": applied, "pulled": pulled}


def apply_hardware_model_async(on_log: Callable[[str], None] | None = None) -> None:
    from llm_client import get_settings
    if not get_settings().get("auto_hardware_model", True):
        if on_log:
            on_log("Auto hardware model disabled — keeping user choice.")
        return
    threading.Thread(target=lambda: apply_hardware_model(on_log=on_log), daemon=True).start()
