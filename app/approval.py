# """
# Human-in-the-loop guardrail.

# This is the single most important file in the project from a hiring
# perspective: it's the difference between "an agent that can do things"
# and "an agent that is safe to point at production." Any action whose
# risk score is above the configured threshold is paused for a human to
# approve or reject before it is allowed to execute.
# """
# from __future__ import annotations

# import os

# from app.cache import Cache

# AUTO_APPROVE_RISK_THRESHOLD = float(os.getenv("AUTO_APPROVE_RISK_THRESHOLD", "0.3"))

# # How long a pending approval survives before it's considered stale.
# # Prevents an abandoned task from sitting in Redis forever.
# APPROVAL_TTL_SECONDS = int(os.getenv("APPROVAL_TTL_SECONDS", str(24 * 60 * 60)))

# # Action types that always require a human, regardless of risk score —
# # e.g. anything that sends a message externally or changes prod code.
# ALWAYS_REVIEW_ACTIONS = {"merge_pr", "send_email", "delete_resource", "post_public_message"}


# def score_risk(action: dict) -> float:
#     """
#     Deterministic risk scoring so the same action always gets the same
#     score (auditable), rather than asking an LLM to grade its own homework.
#     """
#     action_type = action.get("type", "")
#     base_scores = {
#         "post_comment": 0.15,
#         "open_pr": 0.35,
#         "merge_pr": 0.85,
#         "notify_slack": 0.10,
#         "send_email": 0.70,
#         "delete_resource": 0.95,
#         "close_issue": 0.25,
#     }
#     score = base_scores.get(action_type, 0.5)

#     # Bump risk if the action touches production-sounding targets.
#     target = str(action.get("target", "")).lower()
#     if any(word in target for word in ("prod", "main", "master", "release")):
#         score = min(1.0, score + 0.2)

#     return round(score, 2)


# def needs_human_approval(action: dict, risk_score: float | None = None) -> bool:
#     if action.get("type") in ALWAYS_REVIEW_ACTIONS:
#         return True
#     score = risk_score if risk_score is not None else score_risk(action)
#     return score > AUTO_APPROVE_RISK_THRESHOLD


# class ApprovalStore:
#     """
#     Pending human-approval queue, backed by Redis when REDIS_URL is set
#     (survives restarts, shared across every worker/instance) and by an
#     in-process dict otherwise. Without Redis, a task awaiting approval on
#     one Render worker would be invisible to a request handled by a
#     different worker, or would vanish entirely on a redeploy -- this is
#     a real bug the in-memory-only version had, not a hypothetical one.
#     """

#     _KEY_PREFIX = "approval:"

#     def __init__(self, cache: Cache | None = None):
#         self._cache = cache or Cache(namespace="agentops")

#     def add(self, task_id: str, action: dict, risk_score: float) -> None:
#         self._cache.set_json(
#             f"{self._KEY_PREFIX}{task_id}",
#             {"action": action, "risk_score": risk_score},
#             ttl_seconds=APPROVAL_TTL_SECONDS,
#         )

#     def resolve(self, task_id: str, approved: bool) -> dict | None:
#         if approved is None:
#             return None
#         value = self._cache.get_json(f"{self._KEY_PREFIX}{task_id}")
#         if value is not None:
#             self._cache.delete(f"{self._KEY_PREFIX}{task_id}")
#         return value

#     def pending(self) -> dict[str, dict]:
#         result = {}
#         for key in self._cache.keys(self._KEY_PREFIX):
#             task_id = key[len(self._KEY_PREFIX):]
#             value = self._cache.get_json(key)
#             if value is not None:
#                 result[task_id] = value
#         return result

#     def clear(self) -> None:
#         """Test convenience — removes every pending approval."""
#         for key in self._cache.keys(self._KEY_PREFIX):
#             self._cache.delete(key)

#     @property
#     def backend(self) -> str:
#         return self._cache.backend_name


# approval_store = ApprovalStore()








"""
Human-in-the-loop approval guardrail.

External actions are risk-scored deterministically. Actions above the
configured threshold require human approval before execution.

Informational tasks represented by no_action do not require approval
because they do not perform external operations.
"""
from __future__ import annotations

import os

from app.cache import Cache


# Actions above this risk score require human approval.
AUTO_APPROVE_RISK_THRESHOLD = float(
    os.getenv("AUTO_APPROVE_RISK_THRESHOLD", "0.3")
)

# How long a pending approval remains available.
APPROVAL_TTL_SECONDS = int(
    os.getenv("APPROVAL_TTL_SECONDS", str(24 * 60 * 60))
)

# These actions always require human approval, regardless of risk score.
ALWAYS_REVIEW_ACTIONS = {
    "merge_pr",
    "send_email",
    "delete_resource",
    "post_public_message",
}


# Deterministic risk scores for supported actions.
BASE_RISK_SCORES = {
    "no_action": 0.0,
    "post_comment": 0.15,
    "open_pr": 0.35,
    "merge_pr": 0.85,
    "notify_slack": 0.10,
    "send_email": 0.70,
    "delete_resource": 0.95,
    "close_issue": 0.25,
    "post_public_message": 0.80,
}


def score_risk(action: dict) -> float:
    """
    Calculate a deterministic risk score between 0.0 and 1.0.

    The same action always receives the same score.

    no_action has zero risk because it performs no external operation.
    """
    if not isinstance(action, dict):
        return 0.5

    action_type = action.get("type", "")

    # Informational tasks must never inherit the default risk score.
    if action_type == "no_action":
        return 0.0

    score = BASE_RISK_SCORES.get(action_type, 0.5)

    # Increase risk when an action targets a sensitive environment.
    target = str(action.get("target", "")).lower()

    if any(
        word in target
        for word in ("prod", "main", "master", "release")
    ):
        score = min(1.0, score + 0.2)

    return round(score, 2)


def needs_human_approval(
    action: dict,
    risk_score: float | None = None,
) -> bool:
    """
    Determine whether an action requires human approval.

    Rules:
    1. no_action never requires approval.
    2. Mandatory-review actions always require approval.
    3. Other actions require approval when risk exceeds the threshold.
    """
    if not isinstance(action, dict):
        return True

    action_type = action.get("type")

    if action_type == "no_action":
        return False

    if action_type in ALWAYS_REVIEW_ACTIONS:
        return True

    score = (
        risk_score
        if risk_score is not None
        else score_risk(action)
    )

    return score > AUTO_APPROVE_RISK_THRESHOLD


class ApprovalStore:
    """
    Persistent pending-approval queue.

    Uses Redis when REDIS_URL is configured. Otherwise, Cache provides
    the configured fallback backend.

    Pending approvals expire after APPROVAL_TTL_SECONDS.
    """

    _KEY_PREFIX = "approval:"

    def __init__(self, cache: Cache | None = None):
        self._cache = cache or Cache(namespace="agentops")

    def add(
        self,
        task_id: str,
        action: dict,
        risk_score: float,
    ) -> None:
        """
        Store an action awaiting human approval.

        Informational no_action tasks are deliberately excluded.
        """
        if action.get("type") == "no_action":
            return

        self._cache.set_json(
            f"{self._KEY_PREFIX}{task_id}",
            {
                "action": action,
                "risk_score": risk_score,
            },
            ttl_seconds=APPROVAL_TTL_SECONDS,
        )

    def resolve(
        self,
        task_id: str,
        approved: bool,
    ) -> dict | None:
        """
        Resolve a pending approval.

        Returns the stored action and risk score, or None when the
        task has no pending approval.
        """
        if approved is None:
            return None

        key = f"{self._KEY_PREFIX}{task_id}"

        value = self._cache.get_json(key)

        if value is not None:
            self._cache.delete(key)

        return value

    def pending(self) -> dict[str, dict]:
        """Return all currently pending approvals."""
        result = {}

        for key in self._cache.keys(self._KEY_PREFIX):
            task_id = key[len(self._KEY_PREFIX):]
            value = self._cache.get_json(key)

            if value is not None:
                result[task_id] = value

        return result

    def clear(self) -> None:
        """Remove all pending approvals. Intended for tests."""
        for key in self._cache.keys(self._KEY_PREFIX):
            self._cache.delete(key)

    @property
    def backend(self) -> str:
        """Return the active approval-store backend name."""
        return self._cache.backend_name


# Shared approval store used by the application.
approval_store = ApprovalStore()
