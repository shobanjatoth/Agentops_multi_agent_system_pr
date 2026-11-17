"""
Shared state object passed between every node in the LangGraph.

Using a TypedDict (rather than a loose dict) means every agent node gets
autocomplete + type-checking on what it reads and writes, and the graph
compiler can validate the schema at build time.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class ToolCallRecord(TypedDict):
    tool: str
    input: dict
    output: dict
    latency_ms: float


class AgentTrace(TypedDict):
    node: str
    input_summary: str
    output_summary: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    passed: bool


class AgentState(TypedDict, total=False):
    # ---- input ----
    task_id: str
    description: str
    repo: Optional[str]

    # ---- triage ----
    category: Literal["bug", "feature", "question", "incident"]
    priority: Literal["low", "medium", "high", "critical"]

    # ---- research ----
    context_snippets: list[str]
    tool_calls: list[ToolCallRecord]
    injection_flagged: bool

    # ---- action ----
    proposed_action: dict[str, Any]  # e.g. {"type": "post_comment", "body": "..."}
    risk_score: float  # 0.0 (safe) - 1.0 (dangerous)
    action_passed: bool

    # ---- critic ----
    critic_passed: bool
    critic_feedback: str
    revision_count: int

    # ---- approval ----
    requires_human_approval: bool
    approved: Optional[bool]

    # ---- final ----
    status: Literal["pending", "in_progress", "awaiting_approval", "done", "failed"]
    final_result: Optional[str]

    # ---- observability ----
    trace: list[AgentTrace]
