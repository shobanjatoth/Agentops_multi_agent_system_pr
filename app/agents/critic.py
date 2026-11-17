# """
# Critic Agent

# Deterministic guardrail checks — deliberately NOT another LLM call
# grading the first LLM's homework (that pattern is unreliable and
# expensive). Hard rules the action must pass before it's even eligible
# to reach the approval gate or execute.
# """
# from __future__ import annotations

# from app.eval_tracker import EvalTracker
# from app.security import scan_for_secrets
# from app.state import AgentState

# MAX_REVISIONS = 3
# BANNED_PHRASES = ("i cannot", "as an ai", "i'm sorry, but i")
# VALID_ACTION_TYPES = {
#     "post_comment", "open_pr", "notify_slack", "close_issue",
#     "merge_pr", "send_email", "delete_resource", "post_public_message",
# }


# def _check_action(action: dict) -> tuple[bool, str]:
#     if action.get("type") not in VALID_ACTION_TYPES:
#         return False, f"Unknown action type '{action.get('type')}'"
#     if not action.get("body", "").strip():
#         return False, "Action body is empty"
#     if len(action.get("body", "")) > 2000:
#         return False, "Action body exceeds 2000 characters"
#     lowered = action.get("body", "").lower()
#     if any(phrase in lowered for phrase in BANNED_PHRASES):
#         return False, "Action body contains a low-quality LLM disclaimer phrase"
#     # Security check: never let an outbound action (public comment, Slack
#     # message) go out if it contains something that looks like a secret --
#     # whether hallucinated, copied from tool output, or planted via a
#     # prompt-injection attempt in the research context.
#     has_secret, kinds = scan_for_secrets(action.get("body", ""))
#     if has_secret:
#         return False, f"Action body appears to contain a secret/credential ({', '.join(kinds)}) -- blocked"
#     return True, "OK"


# def critic_node(state: AgentState, tracker: EvalTracker) -> AgentState:
#     action = state.get("proposed_action", {})
#     passed, feedback = _check_action(action)
#     revision_count = state.get("revision_count", 0)

#     tracker.log_node(
#         node="critic",
#         input_summary=str(action),
#         output_summary=feedback,
#         latency_ms=0.5,  # deterministic check, effectively instant
#         passed=passed,
#     )

#     return {
#         **state,
#         "critic_passed": passed,
#         "critic_feedback": feedback,
#         "revision_count": revision_count + (0 if passed else 1),
#         "trace": state.get("trace", [])
#         + [
#             {
#                 "node": "critic",
#                 "input_summary": str(action)[:200],
#                 "output_summary": feedback,
#                 "latency_ms": 0.5,
#                 "input_tokens": 0,
#                 "output_tokens": 0,
#                 "cost_usd": 0.0,
#                 "passed": passed,
#             }
#         ],
#     }


# def should_retry(state: AgentState) -> bool:
#     return not state.get("critic_passed", False) and state.get("revision_count", 0) < MAX_REVISIONS









"""
Critic Agent

Deterministic guardrail checks — deliberately NOT another LLM call
grading the first LLM's homework.

Validates proposed actions before they can reach the approval gate
or execute. Informational tasks with no external action are allowed
to pass without outbound-action checks.
"""
from __future__ import annotations

from app.eval_tracker import EvalTracker
from app.security import scan_for_secrets
from app.state import AgentState

MAX_REVISIONS = 3

BANNED_PHRASES = (
    "i cannot",
    "as an ai",
    "i'm sorry, but i",
)

VALID_ACTION_TYPES = {
    "post_comment",
    "open_pr",
    "notify_slack",
    "close_issue",
    "merge_pr",
    "send_email",
    "delete_resource",
    "post_public_message",
    "no_action",
}


def _check_action(action: dict) -> tuple[bool, str]:
    """
    Validate a proposed action.

    no_action is valid because informational tasks do not require
    an external operation.
    """
    if not isinstance(action, dict):
        return False, "Proposed action must be a dictionary"

    action_type = action.get("type")

    # Research-only or informational task.
    # No outbound operation needs to be validated.
    if action_type == "no_action":
        return True, "No external action requested."

    if action_type not in VALID_ACTION_TYPES:
        return False, f"Unknown action type '{action_type}'"

    body = action.get("body", "")

    if not isinstance(body, str) or not body.strip():
        return False, "Action body is empty"

    if len(body) > 2000:
        return False, "Action body exceeds 2000 characters"

    lowered = body.lower()

    if any(phrase in lowered for phrase in BANNED_PHRASES):
        return False, (
            "Action body contains a low-quality LLM disclaimer phrase"
        )

    # Prevent secrets or credentials from reaching external systems.
    has_secret, kinds = scan_for_secrets(body)

    if has_secret:
        return False, (
            "Action body appears to contain a secret/credential "
            f"({', '.join(kinds)}) -- blocked"
        )

    return True, "OK"


def critic_node(
    state: AgentState,
    tracker: EvalTracker,
) -> AgentState:
    """
    Run deterministic validation on the proposed action.
    """
    action = state.get("proposed_action", {})

    passed, feedback = _check_action(action)

    revision_count = state.get("revision_count", 0)

    tracker.log_node(
        node="critic",
        input_summary=str(action),
        output_summary=feedback,
        latency_ms=0.5,
        passed=passed,
    )

    return {
        **state,
        "critic_passed": passed,
        "critic_feedback": feedback,
        "revision_count": (
            revision_count if passed else revision_count + 1
        ),
        "trace": state.get("trace", [])
        + [
            {
                "node": "critic",
                "input_summary": str(action)[:200],
                "output_summary": feedback,
                "latency_ms": 0.5,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "passed": passed,
            }
        ],
    }


def should_retry(state: AgentState) -> bool:
    """
    Retry rejected actions while the revision limit has not been reached.
    """
    return (
        not state.get("critic_passed", False)
        and state.get("revision_count", 0) < MAX_REVISIONS
    )

