# """
# The supervisor graph.

# This is the file that turns four separate functions into a single
# *system*: it decides routing (does a failed critic check go back to the
# Action Agent or stop? does a risky action pause for a human?) instead of
# leaving that logic scattered across the API layer.
# """
# from __future__ import annotations

# from langgraph.graph import END, StateGraph

# from app.agents.action import action_node
# from app.agents.critic import critic_node, should_retry
# from app.agents.research import research_node
# from app.agents.triage import triage_node
# from app.approval import needs_human_approval
# from app.eval_tracker import EvalTracker
# from app.llm import LLMClient
# from app.state import AgentState
# from app.tools.base import ToolRegistry
# from app.tools.github_tool import GitHubTool
# from app.tools.slack_tool import SlackTool


# def build_tool_registry() -> ToolRegistry:
#     registry = ToolRegistry()
#     registry.register(GitHubTool())
#     registry.register(SlackTool())
#     return registry


# def build_graph(tracker: EvalTracker, llm: LLMClient | None = None, tools: ToolRegistry | None = None):
#     """
#     Returns a compiled LangGraph app. `tracker` is bound per-task (one
#     EvalTracker instance = one row per node call, all sharing task_id).
#     """
#     llm = llm or LLMClient()
#     tools = tools or build_tool_registry()

#     graph = StateGraph(AgentState)

#     graph.add_node("triage", lambda state: triage_node(state, tracker, llm))
#     graph.add_node("research", lambda state: research_node(state, tracker, tools))
#     graph.add_node("action", lambda state: action_node(state, tracker, llm))
#     graph.add_node("critic", lambda state: critic_node(state, tracker))
#     graph.add_node("gate", _approval_gate_node)
#     graph.add_node("mark_failed", _mark_failed_node)

#     graph.set_entry_point("triage")
#     graph.add_edge("triage", "research")
#     graph.add_edge("research", "action")
#     graph.add_edge("action", "critic")

#     graph.add_conditional_edges(
#         "critic",
#         _route_after_critic,
#         {"retry": "action", "gate": "gate", "fail": "mark_failed"},
#     )
#     graph.add_edge("gate", END)
#     graph.add_edge("mark_failed", END)

#     return graph.compile()


# def _approval_gate_node(state: AgentState) -> AgentState:
#     action = state["proposed_action"]
#     risk_score = state["risk_score"]
#     requires_approval = needs_human_approval(action, risk_score)

#     return {
#         **state,
#         "requires_human_approval": requires_approval,
#         "status": "awaiting_approval" if requires_approval else "done",
#         "approved": None if requires_approval else True,
#         "final_result": None if requires_approval else f"Auto-approved: {action['type']} executed.",
#     }


# def _mark_failed_node(state: AgentState) -> AgentState:
#     """
#     Reached only when the critic rejects an action MAX_REVISIONS times in a
#     row. Without this node the graph would route straight to END and the
#     task would be left stuck at whatever status it had before the critic
#     ran (a real bug the benchmark script caught) — this makes the failure
#     explicit and auditable instead.
#     """
#     return {
#         **state,
#         "status": "failed",
#         "final_result": f"Failed after {state.get('revision_count', 0)} revision(s): "
#         f"{state.get('critic_feedback', 'action repeatedly rejected by critic')}",
#     }


# def _route_after_critic(state: AgentState) -> str:
#     if state.get("critic_passed"):
#         return "gate"
#     if should_retry(state):
#         return "retry"
#     return "fail"











from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.action import action_node
from app.agents.critic import critic_node, should_retry
from app.agents.research import research_node
from app.agents.triage import triage_node
from app.approval import needs_human_approval
from app.eval_tracker import EvalTracker
from app.llm import LLMClient
from app.state import AgentState
from app.tools.base import ToolRegistry
from app.tools.github_tool import GitHubTool
from app.tools.slack_tool import SlackTool


def build_tool_registry(mocked: bool | None = None) -> ToolRegistry:
    """
    Build the integration registry.

    mocked=None:
        Automatically use credentials from the environment.

    mocked=True:
        Force mock integrations. Safe for benchmarks and tests.

    mocked=False:
        Force real integrations.
    """
    registry = ToolRegistry()

    registry.register(GitHubTool(mocked=mocked))
    registry.register(SlackTool(mocked=mocked))

    return registry


def build_graph(
    tracker: EvalTracker,
    llm: LLMClient | None = None,
    tools: ToolRegistry | None = None,
):
    """
    Build and compile the LangGraph workflow.

    One EvalTracker instance is bound per task.
    """
    llm = llm or LLMClient()
    tools = tools or build_tool_registry()

    graph = StateGraph(AgentState)

    graph.add_node(
        "triage",
        lambda state: triage_node(state, tracker, llm),
    )
    graph.add_node(
        "research",
        lambda state: research_node(state, tracker, tools),
    )
    graph.add_node(
        "action",
        lambda state: action_node(state, tracker, llm),
    )
    graph.add_node(
        "critic",
        lambda state: critic_node(state, tracker),
    )
    graph.add_node("gate", _approval_gate_node)
    graph.add_node("mark_failed", _mark_failed_node)

    graph.set_entry_point("triage")

    graph.add_edge("triage", "research")
    graph.add_edge("research", "action")
    graph.add_edge("action", "critic")

    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {
            "retry": "action",
            "gate": "gate",
            "fail": "mark_failed",
        },
    )

    graph.add_edge("gate", END)
    graph.add_edge("mark_failed", END)

    return graph.compile()


def _approval_gate_node(state: AgentState) -> AgentState:
    action = state["proposed_action"]
    risk_score = state["risk_score"]

    requires_approval = needs_human_approval(
        action,
        risk_score,
    )

    return {
        **state,
        "requires_human_approval": requires_approval,
        "status": (
            "awaiting_approval" if requires_approval else "done"
        ),
        "approved": None if requires_approval else True,
        "final_result": (
            None
            if requires_approval
            else f"Auto-approved: {action['type']} executed."
        ),
    }


def _mark_failed_node(state: AgentState) -> AgentState:
    return {
        **state,
        "status": "failed",
        "final_result": (
            f"Failed after {state.get('revision_count', 0)} revision(s): "
            f"{state.get('critic_feedback', 'action repeatedly rejected by critic')}"
        ),
    }


def _route_after_critic(state: AgentState) -> str:
    if state.get("critic_passed"):
        return "gate"

    if should_retry(state):
        return "retry"

    return "fail"
