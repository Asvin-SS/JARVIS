"""Central configuration — paths, timeouts, and runtime defaults."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Data directories (created on startup)
LOGS_DIR = BASE_DIR / "logs"
BACKUPS_DIR = BASE_DIR / "backups"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
GENERATED_TOOLS_DIR = BASE_DIR / "generated_tools"
CAPABILITY_REGISTRY_DIR = BASE_DIR / "capability_registry"
SELF_UPGRADE_DIR = BASE_DIR / "self_upgrade"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

# LLM / HTTP — 1 hour default per Phase 2 spec
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT_SEC = int(os.environ.get("OLLAMA_TIMEOUT_SEC", "3600"))
LLM_HTTP_TIMEOUT_SEC = int(os.environ.get("LLM_HTTP_TIMEOUT", "3600"))
OLLAMA_MAX_RETRIES = int(os.environ.get("OLLAMA_MAX_RETRIES", "3"))
OLLAMA_RETRY_BACKOFF_BASE = float(os.environ.get("OLLAMA_RETRY_BACKOFF", "2.0"))

# Context limits
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "24"))
MAX_TOOLS_PER_REQUEST = int(os.environ.get("MAX_TOOLS_PER_REQUEST", "12"))

# Model roles (Ollama names — override in settings.json)
MODEL_ROLES = {
    "coding": os.environ.get("JARVIS_MODEL_CODING", "codellama:latest"),
    "reasoning": os.environ.get("JARVIS_MODEL_REASONING", "deepseek-r1:latest"),
    "vision": os.environ.get("JARVIS_MODEL_VISION", "llava:latest"),
    "summary": os.environ.get("JARVIS_MODEL_SUMMARY", "mistral:latest"),
    "general": os.environ.get("JARVIS_MODEL_GENERAL", "mistral:latest"),
}


def ensure_runtime_dirs() -> None:
    """Create runtime folders if missing (safe to call repeatedly)."""
    for d in (
        LOGS_DIR,
        BACKUPS_DIR,
        SNAPSHOTS_DIR,
        GENERATED_TOOLS_DIR,
        CAPABILITY_REGISTRY_DIR,
        SELF_UPGRADE_DIR,
        KNOWLEDGE_DIR / "optimizely",
    ):
        d.mkdir(parents=True, exist_ok=True)
