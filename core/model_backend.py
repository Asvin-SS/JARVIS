# core/model_backend.py
"""
Thin compatibility shim.
All real logic lives in llm_client.py.
Import from here if existing action modules reference model_backend.
"""
from llm_client import unified_chat, chat_with_tools, get_active_model  # noqa: F401