"""
Triage Agent

Deterministic keyword scoring first (fast, free, auditable); only falls
back to an LLM call when the deterministic pass is ambiguous. This
mirrors the "4 deterministic + 3 LLM-backed" pattern already used in
the AI Career Copilot project — cheaper and more predictable than
routing every decision through an LLM.
"""
from __future__ import annotations

from app.eval_tracker import EvalTracker
from app.llm import LLMClient
from app.state import AgentState

INCIDENT_KEYWORDS = {"down", "outage", "crash", "500", "fails", "broken", "not working"}
FEATURE_KEYWORDS = {"add", "support for", "would be nice", "feature request", "enhancement"}
QUESTION_KEYWORDS = {"how do i", "is it possible", "documentation", "?"}

PRIORITY_KEYWORDS = {
    "critical": {"outage", "all users", "production down", "data loss", "security"},
    "high": {"many users", "login", "payment", "checkout"},
}


def _keyword_category(text: str) -> str | None:
    lowered = text.lower()
    if any(k in lowered for k in INCIDENT_KEYWORDS):
        return "bug"
    if any(k in lowered for k in FEATURE_KEYWORDS):
        return "feature"
    if any(k in lowered for k in QUESTION_KEYWORDS):
        return "question"
    return None


def _keyword_priority(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in PRIORITY_KEYWORDS["critical"]):
        return "critical"
    if any(k in lowered for k in PRIORITY_KEYWORDS["high"]):
        return "high"
    return "medium"


def triage_node(state: AgentState, tracker: EvalTracker, llm: LLMClient | None = None) -> AgentState:
    description = state["description"]

    category = _keyword_category(description)
    used_llm = False
    input_tokens = output_tokens = 0
    cost_usd = 0.0
    latency_ms = 0.0

    if category is None:
        # Ambiguous case — fall back to the LLM for classification.
        used_llm = True
        client = llm or LLMClient()
        result = client.complete(
            system="Classify the ticket into exactly one word: bug, feature, or question. "
            "Reply with only that single word.",
            prompt=description,
            max_tokens=5,
        )
        category = result.text.strip().lower()
        if category not in ("bug", "feature", "question"):
            category = "bug"
        input_tokens, output_tokens, latency_ms = (
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
        )
        cost_usd = result.cost_usd

    priority = _keyword_priority(description)

    tracker.log_node(
        node="triage",
        input_summary=description,
        output_summary=f"category={category}, priority={priority}, llm_used={used_llm}",
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        passed=True,
    )

    return {
        **state,
        "category": category,  # type: ignore[typeddict-item]
        "priority": priority,  # type: ignore[typeddict-item]
        "status": "in_progress",
        "trace": state.get("trace", [])
        + [
            {
                "node": "triage",
                "input_summary": description[:200],
                "output_summary": f"{category}/{priority}",
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "passed": True,
            }
        ],
    }
