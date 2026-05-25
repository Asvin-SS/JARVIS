# Best local open-source models for Mark-XXXIX

| Role | Model | Size | Install |
|------|--------|------|---------|
| **General + coding (default)** | `mistral:latest` or `llama3.2` | ~4–5 GB | `ollama pull mistral` |
| **Coding / Optimizely / .NET** | `codellama:latest` | ~4 GB | `ollama pull codellama` |
| **Reasoning / debug** | `deepseek-r1:latest` | ~7 GB | `ollama pull deepseek-r1` |
| **Screen vision** | `llava:latest` | ~4 GB | `ollama pull llava` |
| **Low RAM** | `phi3` or `tinyllama` | 0.6–2 GB | `ollama pull phi3` |

**Recommended stack for SS:** `llama3.2` or `mistral` for chat + tools, `codellama` when editing code, `llava` for screen — set in **Settings → Models**.

Set active model in Settings; vision uses `llava` automatically for screen commands.
