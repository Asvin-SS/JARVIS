"""
Multi-agent orchestration (Phase 7 foundation).

Routes user intent to specialized agent roles without replacing main.py loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentPlan:
    intent: str
    agents: list[str]
    steps: list[str]
    notes: str = ""


def infer_plan(user_text: str) -> AgentPlan:
    """Keyword planner — extended later with LLM planner agent."""
    t = (user_text or "").lower()
    agents: list[str] = ["planner"]
    steps: list[str] = []
    intent = "general"

    if any(k in t for k in ("optimizely", "configured commerce", "elastic", "iis", "sql server", ".net")):
        intent = "enterprise_commerce"
        agents = ["planner", "architect", "search_agent", "coding"]
        steps = [
            "Review Optimizely / ElasticSearch context",
            "Identify handlers, extensions, or ranking changes",
            "Propose safe implementation with rollback",
        ]
    elif any(k in t for k in ("code", "debug", "refactor", "fix", "implement", "build")):
        intent = "coding"
        agents = ["planner", "coding", "reviewer"]
        steps = ["Inspect relevant files", "Propose patch with diff", "Request approval before apply"]
    elif any(k in t for k in ("deploy", "azure", "iis", "pipeline", "ci/cd")):
        intent = "devops"
        agents = ["planner", "devops", "reviewer"]
        steps = ["Validate environment", "Run diagnostics", "Suggest deployment steps"]
    elif any(k in t for k in ("screen", "screenshot", "look at")):
        intent = "vision"
        agents = ["planner", "ui_agent"]
        steps = ["Capture screen", "Analyze with vision model", "Summarize for SS"]
    else:
        steps = ["Answer directly", "Offer task tracking if applicable"]

    return AgentPlan(intent=intent, agents=agents, steps=steps)


def enrich_system_prompt(base: str, user_text: str) -> str:
    """Inject agent plan into system prompt for smarter replies."""
    plan = infer_plan(user_text)
    extra = (
        f"\n[AGENT PLAN]\nIntent: {plan.intent}\n"
        f"Agents: {', '.join(plan.agents)}\n"
        f"Steps: {'; '.join(plan.steps)}\n"
    )
    return base + extra
