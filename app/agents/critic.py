
# """
# Critic Agent

# Deterministic guardrail checks — deliberately NOT another LLM call
# grading the first LLM's homework.

# Validates proposed actions before they can reach the approval gate
# or execute. Informational tasks with no external action are allowed
# to pass without outbound-action checks.
# """
# from __future__ import annotations

# from app.eval_tracker import EvalTracker
# from app.security import scan_for_secrets
# from app.state import AgentState

# MAX_REVISIONS = 3

# BANNED_PHRASES = (
#     "i cannot",
#     "as an ai",
#     "i'm sorry, but i",
# )

# VALID_ACTION_TYPES = {
#     "post_comment",
#     "open_pr",
#     "notify_slack",
#     "close_issue",
#     "merge_pr",
#     "send_email",
#     "delete_resource",
#     "post_public_message",
#     "no_action",
# }


# def _check_action(action: dict) -> tuple[bool, str]:
#     """
#     Validate a proposed action.

#     no_action is valid because informational tasks do not require
#     an external operation.
#     """
#     if not isinstance(action, dict):
#         return False, "Proposed action must be a dictionary"

#     action_type = action.get("type")

#     # Research-only or informational task.
#     # No outbound operation needs to be validated.
#     if action_type == "no_action":
#         return True, "No external action requested."

#     if action_type not in VALID_ACTION_TYPES:
#         return False, f"Unknown action type '{action_type}'"

#     body = action.get("body", "")

#     if not isinstance(body, str) or not body.strip():
#         return False, "Action body is empty"

#     if len(body) > 2000:
#         return False, "Action body exceeds 2000 characters"

#     lowered = body.lower()

#     if any(phrase in lowered for phrase in BANNED_PHRASES):
#         return False, (
#             "Action body contains a low-quality LLM disclaimer phrase"
#         )

#     # Prevent secrets or credentials from reaching external systems.
#     has_secret, kinds = scan_for_secrets(body)

#     if has_secret:
#         return False, (
#             "Action body appears to contain a secret/credential "
#             f"({', '.join(kinds)}) -- blocked"
#         )

#     return True, "OK"


# def critic_node(
#     state: AgentState,
#     tracker: EvalTracker,
# ) -> AgentState:
#     """
#     Run deterministic validation on the proposed action.
#     """
#     action = state.get("proposed_action", {})

#     passed, feedback = _check_action(action)

#     revision_count = state.get("revision_count", 0)

#     tracker.log_node(
#         node="critic",
#         input_summary=str(action),
#         output_summary=feedback,
#         latency_ms=0.5,
#         passed=passed,
#     )

#     return {
#         **state,
#         "critic_passed": passed,
#         "critic_feedback": feedback,
#         "revision_count": (
#             revision_count if passed else revision_count + 1
#         ),
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
#     """
#     Retry rejected actions while the revision limit has not been reached.
#     """
#     return (
#         not state.get("critic_passed", False)
#         and state.get("revision_count", 0) < MAX_REVISIONS
#    




















from __future__ import annotations

import re

from app.eval_tracker import EvalTracker
from app.security import scan_for_secrets
from app.state import AgentState


MAX_REVISIONS = 3
MAX_BODY_LENGTH = 2000

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

REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

COMMENT_TARGET_PATTERN = re.compile(
    r"(?:"
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#([1-9]\d*)"
    r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"|[A-Za-z0-9][A-Za-z0-9_-]{0,62}"
    r")"
)


SLACK_CHANNEL_PATTERN = re.compile(r"#[A-Za-z0-9_-]+")

REQUIRED_PR_FIELDS = ("repo", "title", "head", "base")


def _validate_body(body: object) -> tuple[bool, str]:
    if not isinstance(body, str) or not body.strip():
        return False, "Action body is empty"

    if len(body) > MAX_BODY_LENGTH:
        return False, "Action body exceeds 2000 characters"

    lowered_body = body.lower()

    if any(phrase in lowered_body for phrase in BANNED_PHRASES):
        return False, "Action body contains a low-quality LLM disclaimer phrase"

    has_secret, secret_types = scan_for_secrets(body)

    if has_secret:
        return False, (
            "Action body appears to contain a secret/credential "
            f"({', '.join(secret_types)}) -- blocked"
        )

    return True, "OK"


def _validate_pull_request(action: dict) -> tuple[bool, str]:
    for field in REQUIRED_PR_FIELDS:
        value = action.get(field)

        if not isinstance(value, str) or not value.strip():
            return False, f"Pull request field '{field}' is missing"

    if not REPO_PATTERN.fullmatch(action["repo"]):
        return False, "Invalid repository format; expected owner/repository"

    return True, "Valid pull request action"


def _validate_comment(action: dict) -> tuple[bool, str]:
    # Existing comment actions may omit target.
    # If supplied, the target must have a valid GitHub issue format.
    target = action.get("target")

    if target is None or target == "":
        return True, "OK"

    if not isinstance(target, str):
        return False, "Comment target must be a string"

    if not COMMENT_TARGET_PATTERN.fullmatch(target):
        return False, "Invalid comment target format"

    return True, "OK"


def _validate_slack(action: dict) -> tuple[bool, str]:
    target = action.get("target")

    if not isinstance(target, str) or not SLACK_CHANNEL_PATTERN.fullmatch(target):
        return False, "Invalid Slack channel"

    return True, "OK"


def _check_action(action: dict) -> tuple[bool, str]:
    if not isinstance(action, dict):
        return False, "Proposed action must be a dictionary"

    action_type = action.get("type")

    if action_type not in VALID_ACTION_TYPES:
        return False, f"Unknown action type '{action_type}'"

    if action_type == "no_action":
        return True, "No external action requested."

    passed, feedback = _validate_body(action.get("body"))

    if not passed:
        return False, feedback

    validators = {
        "open_pr": _validate_pull_request,
        "post_comment": _validate_comment,
        "notify_slack": _validate_slack,
    }

    validator = validators.get(action_type)

    if validator:
        return validator(action)

    return True, "OK"


def critic_node(
    state: AgentState,
    tracker: EvalTracker,
) -> AgentState:
    action = state.get("proposed_action", {})
    revision_count = state.get("revision_count", 0)

    passed, feedback = _check_action(action)

    tracker.log_node(
        node="critic",
        input_summary=str(action),
        output_summary=feedback,
        latency_ms=0.5,
        passed=passed,
    )

    trace_entry = {
        "node": "critic",
        "input_summary": str(action)[:200],
        "output_summary": feedback,
        "latency_ms": 0.5,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "passed": passed,
    }

    return {
        **state,
        "critic_passed": passed,
        "critic_feedback": feedback,
        "revision_count": revision_count if passed else revision_count + 1,
        "trace": state.get("trace", []) + [trace_entry],
    }


def should_retry(state: AgentState) -> bool:
    return (
        not state.get("critic_passed", False)
        and state.get("revision_count", 0) < MAX_REVISIONS
    )
